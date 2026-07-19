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
from core.heartbeat_writer import HeartbeatWriter
from core.market_data import MarketData
from core.market_signals import MarketSignalAnalyzer
from core.metrics import CANONICAL_RISK_BLOCKED, CANONICAL_SIGNALS_TOTAL
from core.sentiment import SentimentAnalyzer
from core.signals.adapters import from_legacy_signal
from core.signals.envelope import (
    CanonicalSignalEnvelope,
    DataQuality,
    DataQualityStatus,
    SignalClass,
    SignalDirection,
    SignalPriority,
)
from core.signals.registry import CanonicalSignalRegistry
from core.signals.risk_gate import RiskGate
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
    from adapters.signal_publisher import SignalPublisher
    from storage.sqlite_repository import SqliteSignalRepository

    repository = SqliteSignalRepository(config.DB_PATH)
    client = AI4TradeClient()
    publisher = SignalPublisher(client=client, repository=repository)

    return {
        "repository": repository,
        "client": client,
        "publisher": publisher,
        "signal_router": SignalRouter(publisher=publisher),
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
        "canonical_registry": CanonicalSignalRegistry(),
        "risk_gate": RiskGate(),
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
    except Exception as exc:
        log.warning("_fetch_sentiment fehlgeschlagen, verwende Neutral-Score: %s", exc)
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

    hb_writer = HeartbeatWriter("storage/heartbeat.json", component="legacy", extra={"mode": "signal-producer"})
    hb_writer.write(status="starting")
    last_hb_write = time.monotonic()
    hb_write_interval = 30  # seconds

    if not config.AI4TRADE_TOKEN:
        log.error("AI4TRADE_TOKEN nicht gesetzt. Beende.")
        return

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
    canonical_registry = components["canonical_registry"]
    risk_gate = components["risk_gate"]

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
                    # Emit DATA_QUALITY canonical signal
                    try:
                        dq_envelope = CanonicalSignalEnvelope(
                            signal_class=SignalClass.DATA_QUALITY,
                            subtype="feed_health",
                            source="core.market_signals",
                            asset=asset,
                            direction=SignalDirection.NEUTRAL,
                            confidence=0.9,
                            risk_score=0.3,
                            priority=SignalPriority.HIGH,
                            reason_codes=["feed_degraded"],
                            features=market_context.get("feed_health", {}),
                            data_quality=DataQuality(
                                status=DataQualityStatus.DEGRADED,
                            ),
                            actionability={"can_alert": True},
                            invalidation={"max_age_seconds": 3600, "conditions": []},
                            raw_refs=[],
                        )
                        approved, reason, dq_mod = risk_gate.evaluate(dq_envelope)
                        canonical_registry.append(dq_mod)
                        CANONICAL_SIGNALS_TOTAL.labels(
                            **{"class": dq_mod.signal_class.value, "asset": asset},
                        ).inc()
                        if not approved:
                            CANONICAL_RISK_BLOCKED.labels(reason=reason).inc()
                    except Exception as dq_err:
                        log.debug("DATA_QUALITY side-write error: %s", dq_err)

                sentiment_cache, last_sentiment_time = _fetch_sentiment(
                    sentiment_analyzer, sentiment_cache, last_sentiment_time,
                )

                trade_signal = strategy.decide(
                    ta_result, sentiment_cache, asset,
                    ta_result["indicators"]["price"], 0.1,
                    market_context=market_context,
                )

                # --- Canonical side-write (Issue #16) ---
                try:
                    envelope = from_legacy_signal(trade_signal, market_context)
                    approved, reason, mod_envelope = risk_gate.evaluate(envelope)
                    canonical_registry.append(mod_envelope)
                    CANONICAL_SIGNALS_TOTAL.labels(
                        **{"class": mod_envelope.signal_class.value, "asset": asset},
                    ).inc()
                    if not approved:
                        CANONICAL_RISK_BLOCKED.labels(reason=reason).inc()
                except Exception as cs_err:
                    log.debug("Canonical side-write error: %s", cs_err)

                if trade_signal.confidence >= config.CONFIDENCE_THRESHOLD:
                    signal_router.route(trade_signal, targets=["ai4trade", "log"])

            task_handler.process_pending()
            publisher.flush_queue()

            # Periodic file heartbeat for Docker healthcheck
            now_mono = time.monotonic()
            if now_mono - last_hb_write >= hb_write_interval:
                hb_writer.write(status="running")
                last_hb_write = now_mono

        except Exception as e:
            log.error("Signal-Loop Fehler: %s", e)

        shutdown_event.wait(config.DATA_INTERVAL)

    signal_router.flush_queue(timeout=5)
    repository.log_audit("bot_stop")
    repository.close()
    log.info("Signal-Producer beendet.")


if __name__ == "__main__":
    run()
