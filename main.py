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
from core.sentiment import SentimentAnalyzer
from core.strategy import Strategy
from core.technical import TechnicalAnalyzer
from trading.position_state import PositionState
from trading.risk_gate import RiskGate
from trading.signal_router import SignalRouter

log = logging.getLogger("main")

shutdown_event = threading.Event()
msg_queue: queue.Queue = queue.Queue()


def setup_logging() -> None:
    os.makedirs("storage", exist_ok=True)
    root = logging.getLogger()
    root.setLevel(getattr(logging, config.LOG_LEVEL, logging.INFO))
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    root.handlers.clear()
    root.addHandler(logging.StreamHandler())
    root.addHandler(RotatingFileHandler("storage/bot.log", maxBytes=10_000_000, backupCount=5, encoding="utf-8"))


def graceful_shutdown(signum: int, frame) -> None:
    log.info("Shutdown eingeleitet (Signal %d)...", signum)
    shutdown_event.set()


def run() -> None:
    setup_logging()
    log.info("AI4Trade Bot startet...")
    log.info("Mode: %s | Pairs: %s", config.MODE, config.TRADING_PAIRS)

    if config.MODE != "dry_run":
        log.error("Nur dry_run ist unterstuetzt. Beende.")
        return

    if not config.AI4TRADE_TOKEN:
        log.error("AI4TRADE_TOKEN nicht gesetzt. Beende.")
        return

    from adapters.ai4trade_client import AI4TradeClient
    from adapters.signal_publisher import SignalPublisher

    client = AI4TradeClient()
    publisher = SignalPublisher(client=client)
    position_state = PositionState(client=client)
    risk_gate = RiskGate()
    signal_router = SignalRouter(publisher=publisher)
    market_data = MarketData()
    technical = TechnicalAnalyzer()
    sentiment_analyzer = SentimentAnalyzer()
    strategy = Strategy()
    heartbeat = Heartbeat(
        client=client,
        shutdown_event=shutdown_event,
        interval=config.HEARTBEAT_INTERVAL,
        message_queue=msg_queue,
    )
    task_handler = TaskHandler(msg_queue)

    signal_module.signal(signal_module.SIGINT, graceful_shutdown)
    signal_module.signal(signal_module.SIGTERM, graceful_shutdown)

    hb_thread = threading.Thread(target=heartbeat.run, daemon=True, name="heartbeat")
    hb_thread.start()
    log.info("Heartbeat-Thread gestartet")

    last_sentiment = {"score": 0.0, "confidence": 0.0}
    last_sentiment_time = 0.0

    position_state.refresh()

    while not shutdown_event.is_set():
        try:
            for pair in config.TRADING_PAIRS:
                symbol = pair.replace("/", "")
                ohlcv = market_data.get_ohlcv(symbol, "1h", 200)
                ta_result = technical.analyze(ohlcv)

                now = time.time()
                if now - last_sentiment_time >= config.SENTIMENT_INTERVAL:
                    try:
                        headlines = sentiment_analyzer.fetch_headlines()
                        if headlines:
                            last_sentiment = sentiment_analyzer.analyze(headlines)
                        else:
                            last_sentiment = {"score": 0.0, "confidence": 0.0}
                        last_sentiment_time = now
                    except Exception:
                        last_sentiment = {"score": 0.0, "confidence": 0.0}

                trade_signal = strategy.decide(
                    ta_result, last_sentiment, pair,
                    ta_result["indicators"]["price"], 0.1,
                )

                if trade_signal.confidence >= config.CONFIDENCE_THRESHOLD:
                    passed, reason = risk_gate.check(
                        trade_signal, position_state.positions, 100000,
                    )
                    if passed:
                        signal_router.route(trade_signal, targets=["ai4trade", "log"])
                        position_state.refresh()
                    else:
                        log.info("Risk-Gate BLOCK: %s - %s", pair, reason)

            task_handler.process_pending()
            publisher.flush_queue()

        except Exception as e:
            log.error("Trading-Loop Fehler: %s", e)

        shutdown_event.wait(config.DATA_INTERVAL)

    signal_router.flush_queue(timeout=5)
    log.info("Bot beendet.")


if __name__ == "__main__":
    run()
