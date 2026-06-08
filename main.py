import json
import logging
import os
import queue
import signal as signal_module
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from logging.handlers import RotatingFileHandler

import config
from adapters.heartbeat import Heartbeat
from adapters.task_handler import TaskHandler
from core.ai_evaluator_bridge import AIEvaluatorBridge
from core.market_data import MarketData
from core.market_signals import MarketSignalAnalyzer
from core.metrics import LAST_SIGNAL_TIMESTAMP, SIGNALS_PUBLISHED, SIGNALS_TOTAL, get_metrics
from core.outcome_tracker import OutcomeTracker
from core.risk_gate import RiskGate
from core.sentiment import SentimentAnalyzer
from core.strategy import Strategy
from core.technical import TechnicalAnalyzer
from core.whimsy import create_formatter, print_whimsy_banner
from trading.signal_router import SignalRouter

# Main signal producer loop: collect market data, technical signals, sentiment,
# score signals with strategy, and route them for persistence and publishing.
log = logging.getLogger("main")

shutdown_event = threading.Event()
msg_queue: queue.Queue = queue.Queue()

# Global start time for uptime calculation
_bot_start_time: float = 0.0


class HealthHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler returning JSON health + Prometheus metrics."""

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json_health()
        elif self.path == "/metrics":
            self._send_prometheus()
        else:
            self.send_response(404)
            self.end_headers()

    def _send_json_health(self) -> None:
        uptime = time.time() - _bot_start_time if _bot_start_time else 0
        payload = json.dumps({
            "status": "healthy",
            "uptime_seconds": round(uptime, 1),
        })
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(payload.encode())

    def _send_prometheus(self) -> None:
        data = get_metrics()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args) -> None:  # noqa: ANN001
        # Suppress default access logs
        pass


def _start_health_server(port: int) -> None:
    """Start a minimal HTTP server for health + metrics on the given port."""
    from socketserver import ThreadingMixIn

    class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
        daemon_threads = True

    server = ThreadedHTTPServer(("0.0.0.0", port), HealthHandler)
    log.info("Health/Metrics-Server auf Port %d", port)
    server.serve_forever()


def setup_logging() -> None:
    os.makedirs("storage", exist_ok=True)
    root = logging.getLogger()
    root.setLevel(getattr(logging, config.LOG_LEVEL, logging.INFO))
    fmt = create_formatter(config.LOG_FORMAT)
    root.handlers.clear()
    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    root.addHandler(stream)
    file_handler = RotatingFileHandler(
        "storage/bot.log",
        maxBytes=10_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)


def graceful_shutdown(signum: int, frame) -> None:
    log.info("Shutdown eingeleitet (Signal %d)...", signum)
    shutdown_event.set()


def _init_components() -> dict:
    from adapters.ai4trade_client import AI4TradeClient
    from adapters.rainbow_publisher import RainbowApiPublisher
    from adapters.signal_publisher import SignalPublisher
    from storage.sqlite_repository import SqliteSignalRepository

    repository = SqliteSignalRepository(config.DB_PATH)
    client = AI4TradeClient()
    publisher = SignalPublisher(client=client, repository=repository)
    rainbow_publisher = RainbowApiPublisher()

    return {
        "repository": repository,
        "client": client,
        "publisher": publisher,
        "rainbow_publisher": rainbow_publisher,
        "signal_router": SignalRouter(publisher=publisher, rainbow_publisher=rainbow_publisher),
        "market_data": MarketData(),
        "technical": TechnicalAnalyzer(),
        "market_signals": MarketSignalAnalyzer(),
        "sentiment_analyzer": SentimentAnalyzer(),
        "strategy": Strategy(ai_bridge=AIEvaluatorBridge()),
        "risk_gate": RiskGate(),
        "heartbeat": Heartbeat(
            client=client,
            shutdown_event=shutdown_event,
            interval=config.HEARTBEAT_INTERVAL,
            message_queue=msg_queue,
        ),
        "task_handler": TaskHandler(msg_queue),
        "outcome_tracker": OutcomeTracker(
            repository=repository,
            outcome_window_hours=config.OUTCOME_WINDOW_HOURS,
        ),
    }


def _fetch_sentiment(
    analyzer: SentimentAnalyzer,
    cached: dict,
    last_time: float,
) -> tuple[dict, float]:
    now = time.time()
    if now - last_time < config.SENTIMENT_INTERVAL:
        return cached, last_time

    try:
        headlines = analyzer.fetch_headlines()
        if headlines:
            result = analyzer.analyze(headlines)
        else:
            result = {"score": 0.0, "confidence": 0.0}
        return result, now
    except Exception:
        return {"score": 0.0, "confidence": 0.0}, now


def run() -> None:
    """Starte den reinen Signal-Producer.

    Dieser Prozess erstellt Signale aus Markt- und Sentiment-Daten und leitet sie
    an den SignalRouter und den Publisher weiter.
    """
    global _bot_start_time
    _bot_start_time = time.time()

    print_whimsy_banner("AI4Trade Bot", "Signal-Producer fuer kluge Entscheidungen")
    setup_logging()
    log.info("AI4Trade Signal-Producer startet...")
    log.info("Assets: %s", config.ASSETS)

    if not config.AI4TRADE_TOKEN:
        log.warning("AI4TRADE_TOKEN nicht gesetzt — laeuft im Rainbow-only Modus")

    # Start health/metrics HTTP server in background
    metrics_port = config.METRICS_PORT
    health_thread = threading.Thread(
        target=_start_health_server,
        args=(metrics_port,),
        daemon=True,
        name="health_server",
    )
    health_thread.start()

    components = _init_components()
    repository = components["repository"]
    publisher = components["publisher"]
    signal_router = components["signal_router"]
    market_data = components["market_data"]
    technical = components["technical"]
    market_signal_analyzer = components["market_signals"]
    sentiment_analyzer = components["sentiment_analyzer"]
    strategy = components["strategy"]
    risk_gate = components["risk_gate"]
    heartbeat = components["heartbeat"]
    task_handler = components["task_handler"]

    signal_module.signal(signal_module.SIGINT, graceful_shutdown)
    signal_module.signal(signal_module.SIGTERM, graceful_shutdown)

    hb_thread = threading.Thread(target=heartbeat.run, daemon=True, name="heartbeat")
    hb_thread.start()
    log.info("Heartbeat-Thread gestartet")

    outcome_tracker = components["outcome_tracker"]
    outcome_tracker.start()

    repository.log_audit("bot_start", {"assets": config.ASSETS})

    sentiment_cache = {"score": 0.0, "confidence": 0.0}
    last_sentiment_time = 0.0

    while not shutdown_event.is_set():
        try:
            for asset in config.ASSETS:
                symbol = asset.replace("/", "")
                ohlcv = market_data.get_ohlcv(symbol, "1h", 200)
                ta_result = technical.analyze(ohlcv)
                market_context = market_signal_analyzer.analyze(ohlcv, expected_interval_seconds=3600)

                if not market_context["feed_health"]["is_healthy"]:
                    log.warning(
                        "Market-Feed degraded fuer %s: %s",
                        asset,
                        market_context.get("no_trade_reason", "unknown"),
                    )

                sentiment_cache, last_sentiment_time = _fetch_sentiment(
                    sentiment_analyzer,
                    sentiment_cache,
                    last_sentiment_time,
                )

                trade_signal = strategy.decide(
                    ta_result,
                    sentiment_cache,
                    asset,
                    ta_result["indicators"]["price"],
                    0.1,
                    market_context=market_context,
                )

                # Record signal generation metrics
                SIGNALS_TOTAL.labels(pair=trade_signal.pair, action=trade_signal.action).inc()
                LAST_SIGNAL_TIMESTAMP.set(time.time())

                # Risk gate: check signal before routing
                approved, reason = risk_gate.check(trade_signal, market_context)
                if not approved:
                    continue

                if trade_signal.confidence >= config.CONFIDENCE_THRESHOLD:
                    signal_id = repository.log_signal_with_id(trade_signal)
                    log.info(
                        "Signal %s: %s %s confidence=%d price=%.2f",
                        signal_id[:8],
                        trade_signal.pair,
                        trade_signal.action,
                        trade_signal.confidence,
                        trade_signal.price,
                    )
                    signal_router.route(trade_signal, targets=["rainbow_api", "log"])

                    # Record published metrics
                    SIGNALS_PUBLISHED.labels(pair=trade_signal.pair, action=trade_signal.action).inc()

            task_handler.process_pending()
            publisher.flush_queue()

        except Exception as e:
            log.error("Signal-Loop Fehler: %s", e)

        shutdown_event.wait(config.DATA_INTERVAL)

    signal_router.flush_queue(timeout=5)
    repository.log_audit("bot_stop")
    repository.close()
    log.info("Signal-Producer beendet.")


if __name__ == "__main__":
    run()
