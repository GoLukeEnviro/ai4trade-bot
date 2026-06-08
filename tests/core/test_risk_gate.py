# tests/core/test_risk_gate.py
"""Tests for core.risk_gate.RiskGate — signal validation rules."""

from core.risk_gate import RiskGate
from core.signal_model import Signal


def _make_signal(confidence: int = 80, action: str = "BUY") -> Signal:
    return Signal(pair="BTC/USDT", action=action, confidence=confidence, price=50000.0, quantity=0.1)


def _healthy_context() -> dict:
    return {
        "feed_health": {"is_healthy": True},
        "risk_off": False,
        "drawdown_pct": 0.0,
    }


class TestRiskGatePassThrough:
    """Signal passes all checks."""

    def test_approved_when_all_checks_pass(self):
        gate = RiskGate(confidence_threshold=60)
        signal = _make_signal(confidence=80)
        approved, reason = gate.check(signal, _healthy_context())

        assert approved is True
        assert reason == "approved"

    def test_approved_at_exact_threshold(self):
        gate = RiskGate(confidence_threshold=60)
        signal = _make_signal(confidence=60)
        approved, reason = gate.check(signal, _healthy_context())

        assert approved is True
        assert reason == "approved"


class TestRiskGateConfidenceRule:
    """Rule 1: Block if confidence < CONFIDENCE_THRESHOLD."""

    def test_blocked_below_threshold(self):
        gate = RiskGate(confidence_threshold=60)
        signal = _make_signal(confidence=50)
        approved, reason = gate.check(signal, _healthy_context())

        assert approved is False
        assert "confidence" in reason
        assert "50" in reason

    def test_blocked_with_zero_confidence(self):
        gate = RiskGate(confidence_threshold=1)
        signal = _make_signal(confidence=0)
        approved, reason = gate.check(signal, _healthy_context())

        assert approved is False


class TestRiskGateFeedHealthRule:
    """Rule 2: Block if feed_health.is_healthy == False."""

    def test_blocked_when_feed_unhealthy(self):
        gate = RiskGate(confidence_threshold=60)
        signal = _make_signal(confidence=80)
        ctx = _healthy_context()
        ctx["feed_health"]["is_healthy"] = False

        approved, reason = gate.check(signal, ctx)

        assert approved is False
        assert "feed unhealthy" in reason

    def test_passes_when_feed_healthy(self):
        gate = RiskGate(confidence_threshold=60)
        signal = _make_signal(confidence=80)
        ctx = _healthy_context()
        ctx["feed_health"]["is_healthy"] = True

        approved, reason = gate.check(signal, ctx)
        assert approved is True


class TestRiskGateRiskOffRule:
    """Rule 3: Block if risk_off == True in market_context."""

    def test_blocked_when_risk_off(self):
        gate = RiskGate(confidence_threshold=60)
        signal = _make_signal(confidence=80)
        ctx = _healthy_context()
        ctx["risk_off"] = True

        approved, reason = gate.check(signal, ctx)

        assert approved is False
        assert "risk_off" in reason

    def test_passes_when_risk_off_false(self):
        gate = RiskGate(confidence_threshold=60)
        signal = _make_signal(confidence=80)
        ctx = _healthy_context()
        ctx["risk_off"] = False

        approved, reason = gate.check(signal, ctx)
        assert approved is True


class TestRiskGateDrawdownRule:
    """Rule 4: Block if drawdown exceeds MAX_DOWNDRAW_PCT."""

    def test_blocked_when_drawdown_exceeds_max(self):
        gate = RiskGate(confidence_threshold=60, max_drawdown_pct=15.0)
        signal = _make_signal(confidence=80)
        ctx = _healthy_context()
        ctx["drawdown_pct"] = 20.0

        approved, reason = gate.check(signal, ctx)

        assert approved is False
        assert "drawdown" in reason

    def test_passes_at_exact_max_drawdown(self):
        gate = RiskGate(confidence_threshold=60, max_drawdown_pct=15.0)
        signal = _make_signal(confidence=80)
        ctx = _healthy_context()
        ctx["drawdown_pct"] = 15.0

        approved, reason = gate.check(signal, ctx)
        assert approved is True

    def test_passes_below_max_drawdown(self):
        gate = RiskGate(confidence_threshold=60, max_drawdown_pct=15.0)
        signal = _make_signal(confidence=80)
        ctx = _healthy_context()
        ctx["drawdown_pct"] = 10.0

        approved, reason = gate.check(signal, ctx)
        assert approved is True

    def test_default_max_drawdown(self):
        """Default MAX_DOWNDRAW_PCT is 15 from config."""
        gate = RiskGate(confidence_threshold=60)
        signal = _make_signal(confidence=80)
        ctx = _healthy_context()
        ctx["drawdown_pct"] = 16.0

        approved, reason = gate.check(signal, ctx)
        assert approved is False


class TestRiskGateDefaultContext:
    """Behavior with minimal/empty market context."""

    def test_passes_with_empty_context(self):
        """Empty context defaults: healthy feed, no risk_off, 0 drawdown."""
        gate = RiskGate(confidence_threshold=0)
        signal = _make_signal(confidence=50)
        approved, reason = gate.check(signal, {})

        assert approved is True
        assert reason == "approved"

    def test_passes_with_none_context(self):
        """None defaults treated as empty context (strategy.decide does the same)."""
        # RiskGate.check expects a dict, so passing {} is equivalent
        gate = RiskGate(confidence_threshold=0)
        signal = _make_signal(confidence=50)
        approved, reason = gate.check(signal, {})
        assert approved is True


class TestRiskGateMetrics:
    """SIGNALS_BLOCKED counter is incremented on block."""

    def test_blocked_signal_increments_counter(self):
        from core.metrics import SIGNALS_BLOCKED

        gate = RiskGate(confidence_threshold=60)
        signal = _make_signal(confidence=10)

        before = SIGNALS_BLOCKED.labels(pair="BTC/USDT", reason="test")._value.get()
        approved, reason = gate.check(signal, _healthy_context())

        assert approved is False
        # Verify the counter for the actual reason was incremented
        after = SIGNALS_BLOCKED.labels(pair="BTC/USDT", reason=reason)._value.get()
        assert after == before + 1
