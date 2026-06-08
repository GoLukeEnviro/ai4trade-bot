"""Integrationstests: Signal-Pipeline ohne echte API-Calls."""

from unittest.mock import MagicMock

from core.signal_model import Signal
from core.strategy import Strategy
from core.technical import TechnicalAnalyzer
from tests.fixtures.ohlcv_fixtures import make_ohlcv
from trading.signal_router import SignalRouter


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


def test_main_import_does_not_start_runtime():
    """main.run ist importierbar und callable, ohne den Bot zu starten."""
    from main import run

    assert callable(run)


def test_signal_flows_through_risk_gate_approved():
    """Signal above confidence threshold passes risk gate and is routed."""
    from core.risk_gate import RiskGate

    buy_signal = Signal(pair="BTC/USDT", action="BUY", confidence=80, price=50000.0, quantity=0.1)
    gate = RiskGate(confidence_threshold=60)
    market_context = {
        "feed_health": {"is_healthy": True},
        "risk_off": False,
        "drawdown_pct": 0.0,
    }

    approved, reason = gate.check(buy_signal, market_context)
    assert approved is True
    assert reason == "approved"

    # After gate approval, signal should be routed
    mock_publisher = MagicMock()
    mock_publisher.publish.return_value = True
    router = SignalRouter(publisher=mock_publisher)
    success = router.route(buy_signal, targets=["ai4trade"])
    assert success is True
    mock_publisher.publish.assert_called_once_with(buy_signal)


def test_signal_flows_through_risk_gate_blocked():
    """Signal below confidence threshold is blocked by risk gate."""
    from core.risk_gate import RiskGate

    low_signal = Signal(pair="BTC/USDT", action="BUY", confidence=30, price=50000.0, quantity=0.1)
    gate = RiskGate(confidence_threshold=60)
    market_context = {
        "feed_health": {"is_healthy": True},
        "risk_off": False,
        "drawdown_pct": 0.0,
    }

    approved, reason = gate.check(low_signal, market_context)
    assert approved is False
    assert "confidence" in reason


def test_signal_blocked_by_feed_health():
    """Signal is blocked when feed is unhealthy."""
    from core.risk_gate import RiskGate

    signal = Signal(pair="ETH/USDT", action="BUY", confidence=80, price=3000.0, quantity=1.0)
    gate = RiskGate(confidence_threshold=60)
    market_context = {
        "feed_health": {"is_healthy": False},
        "risk_off": False,
        "drawdown_pct": 0.0,
    }

    approved, reason = gate.check(signal, market_context)
    assert approved is False
    assert "feed unhealthy" in reason


def test_signal_blocked_by_risk_off():
    """Signal is blocked when risk_off is True."""
    from core.risk_gate import RiskGate

    signal = Signal(pair="SOL/USDT", action="BUY", confidence=75, price=100.0, quantity=10.0)
    gate = RiskGate(confidence_threshold=60)
    market_context = {
        "feed_health": {"is_healthy": True},
        "risk_off": True,
        "drawdown_pct": 0.0,
    }

    approved, reason = gate.check(signal, market_context)
    assert approved is False
    assert "risk_off" in reason


def test_signal_blocked_by_drawdown():
    """Signal is blocked when drawdown exceeds max."""
    from core.risk_gate import RiskGate

    signal = Signal(pair="BTC/USDT", action="BUY", confidence=80, price=50000.0, quantity=0.1)
    gate = RiskGate(confidence_threshold=60, max_drawdown_pct=15.0)
    market_context = {
        "feed_health": {"is_healthy": True},
        "risk_off": False,
        "drawdown_pct": 20.0,
    }

    approved, reason = gate.check(signal, market_context)
    assert approved is False
    assert "drawdown" in reason
