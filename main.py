import logging
import os
import queue
import signal as signal_module
import threading
import time
from logging.handlers import RotatingFileHandler

import config
from adapters.heartbeat import Heartbeat
from adapters.task_handler import TaskHandler
from core.market_data import MarketData
from core.market_signals import MarketSignalAnalyzer
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
        "storage/bot.log", maxBytes=10_000_000, backupCount=5, encoding="utf-8",
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
        "strategy": Strategy(),
        "heartbeat": Heartbeat(
            client=client,
            shutdown_event=shutdown_event,
            interval=config.HEARTBEAT_INTERVAL,
            message_queue=msg_queue,
        ),
        "task_handler": TaskHandler(msg_queue),
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
    print_whimsy_banner("AI4Trade Bot", "Signal-Producer fuer kluge Entscheidungen")
    setup_logging()
    log.info("AI4Trade Signal-Producer startet...")
    log.info("Assets: %s", config.ASSETS)

    if not config.AI4TRADE_TOKEN:
        log.warning("AI4TRADE_TOKEN nicht gesetzt — laeuft im Rainbow-only Modus")

    components = _init_components()
    repository = components["repository"]
    publisher = components["publisher"]
    signal_router = components["signal_router"]
    market_data = components["market_data"]
    technical = components["technical"]
    market_signal_analyzer = components["market_signals"]
    sentiment_analyzer = components["sentiment_analyzer"]
    strategy = components["strategy"]
    heartbeat = components["heartbeat"]
    task_handler = components["task_handler"]

    signal_module.signal(signal_module.SIGINT, graceful_shutdown)
    signal_module.signal(signal_module.SIGTERM, graceful_shutdown)

    hb_thread = threading.Thread(target=heartbeat.run, daemon=True, name="heartbeat")
    hb_thread.start()
    log.info("Heartbeat-Thread gestartet")

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
                    sentiment_analyzer, sentiment_cache, last_sentiment_time,
                )

                trade_signal = strategy.decide(
                    ta_result, sentiment_cache, asset,
                    ta_result["indicators"]["price"], 0.1,
                    market_context=market_context,
                )

                if trade_signal.confidence >= config.CONFIDENCE_THRESHOLD:
                    signal_router.route(trade_signal, targets=["rainbow_api", "log"])

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
