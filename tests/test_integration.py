# tests/test_integration.py
"""Integrationstests: Validiert Verdrahtung der MVP-Signal-Pipeline ohne echte API-Calls."""
from unittest.mock import MagicMock

from core.technical import TechnicalAnalyzer
from core.strategy import Strategy
from core.signal_model import Signal
from trading.risk_gate import RiskGate
from trading.signal_router import SignalRouter
from tests.fixtures.ohlcv_fixtures import make_ohlcv


def test_full_signal_pipeline():
    """OHLCV -> TA -> Strategy -> RiskGate -> SignalRouter mit gemocktem Publisher."""
    df = make_ohlcv(200, 50000, "up")
    ta = TechnicalAnalyzer()
    strategy = Strategy()
    risk_gate = RiskGate(starting_capital=100000)

    ta_result = ta.analyze(df)
    sentiment = {"score": 0.5, "confidence": 0.8}
    trade_signal = strategy.decide(ta_result, sentiment, "BTC/USDT", 50000.0, 0.1)

    assert trade_signal.action in ("BUY", "SELL", "HOLD")
    assert trade_signal.pair == "BTC/USDT"
    assert trade_signal.mode == "dry_run"

    if trade_signal.action != "HOLD":
        passed, reason = risk_gate.check(trade_signal, [], 100000)
        assert passed is True

        mock_publisher = MagicMock()
        mock_publisher.publish.return_value = True
        router = SignalRouter(publisher=mock_publisher)
        success = router.route(trade_signal, targets=["ai4trade"])
        assert success is True
        mock_publisher.publish.assert_called_once_with(trade_signal)


def test_full_signal_pipeline_with_explicit_buy():
    """Pipeline-Test mit direkt erzeugtem BUY-Signal fuer deterministische Verdrahtung."""
    buy_signal = Signal(pair="BTC/USDT", action="BUY", confidence=80, price=50000.0, quantity=0.1)

    risk_gate = RiskGate(starting_capital=100000)
    passed, reason = risk_gate.check(buy_signal, [], 100000)
    assert passed is True, f"BUY-Signal sollte passieren, aber: {reason}"

    mock_publisher = MagicMock()
    mock_publisher.publish.return_value = True
    router = SignalRouter(publisher=mock_publisher)
    success = router.route(buy_signal, targets=["ai4trade"])
    assert success is True
    mock_publisher.publish.assert_called_once_with(buy_signal)


def test_risk_gate_blocks_pipeline():
    """Restriktiver RiskGate (max_positions=0) blockiert Trading-Signale.
    SignalRouter wird bei Blockade gar nicht aufgerufen (wie in main.py)."""
    df = make_ohlcv(200, 50000, "up")
    ta = TechnicalAnalyzer()
    strategy = Strategy()
    risk_gate = RiskGate(starting_capital=100000, max_positions=0)

    ta_result = ta.analyze(df)
    trade_signal = strategy.decide(ta_result, {"score": 0.9}, "BTC/USDT", 50000.0, 0.1)

    if trade_signal.action != "HOLD":
        passed, reason = risk_gate.check(trade_signal, [], 100000)
        assert passed is False
        assert "max_positions" in reason

        mock_publisher = MagicMock()
        router = SignalRouter(publisher=mock_publisher)
        # Pipeline: bei RiskGate-Block wird route() nicht aufgerufen
        if passed:
            router.route(trade_signal, targets=["ai4trade"])
        mock_publisher.publish.assert_not_called()


def test_risk_gate_blocks_explicit_buy():
    """BUY-Signal wird bei max_positions=0 blockiert und nie an Publisher gesendet."""
    buy_signal = Signal(pair="BTC/USDT", action="BUY", confidence=80, price=50000.0, quantity=0.1)

    risk_gate = RiskGate(starting_capital=100000, max_positions=0)
    passed, reason = risk_gate.check(buy_signal, [], 100000)
    assert passed is False
    assert "max_positions" in reason

    mock_publisher = MagicMock()
    router = SignalRouter(publisher=mock_publisher)
    # Pipeline: bei RiskGate-Block wird route() nicht aufgerufen
    if passed:
        router.route(buy_signal, targets=["ai4trade"])
    mock_publisher.publish.assert_not_called()


def test_all_modules_import():
    """Alle MVP-Module lassen sich fehlerfrei importieren."""
    from core.signal_model import Signal, Intent
    from core.market_data import MarketData
    from core.technical import TechnicalAnalyzer
    from core.sentiment import SentimentAnalyzer
    from core.strategy import Strategy
    from adapters.ai4trade_client import AI4TradeClient
    from adapters.signal_publisher import SignalPublisher
    from adapters.heartbeat import Heartbeat
    from adapters.task_handler import TaskHandler
    from trading.risk_gate import RiskGate
    from trading.position_state import PositionState
    from trading.signal_router import SignalRouter
    from chat.commander import Commander


def test_main_import_does_not_start_runtime():
    """main.run ist importierbar und callable, ohne den Bot zu starten."""
    from main import run
    assert callable(run)
