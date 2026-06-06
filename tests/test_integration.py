"""Integrationstests: Signal-Pipeline ohne echte API-Calls."""
from unittest.mock import MagicMock

from core.signal_model import Signal
from core.technical import TechnicalAnalyzer
from core.strategy import Strategy
from trading.signal_router import SignalRouter
from tests.fixtures.ohlcv_fixtures import make_ohlcv


def test_full_signal_pipeline():
    """OHLCV -> TA -> Strategy -> SignalRouter mit gemocktem Publisher."""
    df = make_ohlcv(200, 50000, "up")
    ta = TechnicalAnalyzer()
    strategy = Strategy()

    ta_result = ta.analyze(df)
    sentiment = {"score": 0.5, "confidence": 0.8}
    trade_signal = strategy.decide(ta_result, sentiment, "BTC/USDT", 50000.0, 0.1)

    assert trade_signal.action in ("BUY", "SELL", "HOLD")
    assert trade_signal.pair == "BTC/USDT"
    assert trade_signal.mode == "dry_run"

    mock_publisher = MagicMock()
    mock_publisher.publish.return_value = True
    router = SignalRouter(publisher=mock_publisher)
    success = router.route(trade_signal, targets=["ai4trade"])

    if trade_signal.action == "HOLD":
        assert success is True
        mock_publisher.publish.assert_not_called()
    else:
        assert success is True
        mock_publisher.publish.assert_called_once_with(trade_signal)


def test_signal_above_confidence_threshold_routed():
    """Signal mit Confidence >= Threshold wird an Publisher gesendet."""
    buy_signal = Signal(pair="BTC/USDT", action="BUY", confidence=80, price=50000.0, quantity=0.1)

    assert buy_signal.confidence >= 60

    mock_publisher = MagicMock()
    mock_publisher.publish.return_value = True
    router = SignalRouter(publisher=mock_publisher)
    success = router.route(buy_signal, targets=["ai4trade"])
    assert success is True
    mock_publisher.publish.assert_called_once_with(buy_signal)


def test_hold_signal_not_routed():
    """HOLD-Signale werden nicht an den Publisher gesendet."""
    hold_signal = Signal(pair="BTC/USDT", action="HOLD", confidence=40, price=50000.0, quantity=0.1)

    mock_publisher = MagicMock()
    router = SignalRouter(publisher=mock_publisher)
    success = router.route(hold_signal, targets=["ai4trade"])

    assert success is True
    mock_publisher.publish.assert_not_called()


def test_all_modules_import():
    """Alle Signal-Pipeline-Module lassen sich fehlerfrei importieren."""
    from core.signal_model import Signal, Intent
    from core.market_data import MarketData
    from core.technical import TechnicalAnalyzer
    from core.sentiment import SentimentAnalyzer
    from core.strategy import Strategy
    from adapters.ai4trade_client import AI4TradeClient
    from adapters.signal_publisher import SignalPublisher
    from adapters.heartbeat import Heartbeat
    from adapters.task_handler import TaskHandler
    from trading.signal_router import SignalRouter
    from chat.commander import Commander


def test_main_import_does_not_start_runtime():
    """main.run ist importierbar und callable, ohne den Bot zu starten."""
    from main import run
    assert callable(run)
