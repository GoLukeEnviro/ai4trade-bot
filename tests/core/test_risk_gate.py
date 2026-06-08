"""Tests for Issue #15 — Risk and Data-Quality Gate."""

from __future__ import annotations

import pytest

from core.signals.envelope import (
    Actionability,
    CanonicalSignalEnvelope,
    DataQuality,
    DataQualityStatus,
    SignalClass,
    SignalDirection,
    SignalPriority,
)
from core.signals.risk_gate import RiskGate

# ======================================================================
# Helpers
# ======================================================================

def _make_envelope(**overrides) -> CanonicalSignalEnvelope:
    defaults = dict(
        signal_class=SignalClass.ENTRY,
        subtype="test",
        source="unit-test",
        asset="BTC/USDT",
        direction=SignalDirection.BULLISH,
        confidence=0.75,
        risk_score=0.3,
        priority=SignalPriority.MEDIUM,
        reason_codes=["test"],
        features={},
        data_quality=DataQuality(status=DataQualityStatus.OK),
        actionability=Actionability(can_alert=True),
        raw_refs=[],
    )
    defaults.update(overrides)
    return CanonicalSignalEnvelope(**defaults)


@pytest.fixture()
def gate() -> RiskGate:
    return RiskGate(min_confidence=0.3)


# ======================================================================
# Rule 1: data quality gate
# ======================================================================

class TestDataQualityGate:
    def test_degraded_blocks(self, gate):
        env = _make_envelope(data_quality=DataQuality(status=DataQualityStatus.DEGRADED))
        approved, reason, _ = gate.evaluate(env)
        assert approved is False
        assert reason == "data_quality_degraded"

    def test_stale_blocks(self, gate):
        env = _make_envelope(data_quality=DataQuality(status=DataQualityStatus.STALE))
        approved, reason, _ = gate.evaluate(env)
        assert approved is False
        assert reason == "data_quality_degraded"

    def test_unavailable_blocks(self, gate):
        env = _make_envelope(data_quality=DataQuality(status=DataQualityStatus.UNAVAILABLE))
        approved, reason, _ = gate.evaluate(env)
        assert approved is False
        assert reason == "data_quality_degraded"

    def test_ok_passes_quality(self, gate):
        env = _make_envelope(data_quality=DataQuality(status=DataQualityStatus.OK))
        approved, reason, _ = gate.evaluate(env)
        # May fail on later rules but not on data_quality
        assert reason != "data_quality_degraded"


# ======================================================================
# Rule 2: high risk
# ======================================================================

class TestHighRiskGate:
    def test_risk_at_threshold_blocks(self, gate):
        env = _make_envelope(risk_score=0.8)
        approved, reason, _ = gate.evaluate(env)
        assert approved is False
        assert reason == "risk_too_high"

    def test_risk_above_threshold_blocks(self, gate):
        env = _make_envelope(risk_score=0.95)
        approved, reason, _ = gate.evaluate(env)
        assert approved is False
        assert reason == "risk_too_high"

    def test_risk_below_threshold_passes(self, gate):
        env = _make_envelope(risk_score=0.79, confidence=0.9)
        approved, reason, _ = gate.evaluate(env)
        assert reason != "risk_too_high"


# ======================================================================
# Rule 3: low confidence
# ======================================================================

class TestLowConfidenceGate:
    def test_below_min_confidence(self, gate):
        env = _make_envelope(confidence=0.2)
        approved, reason, _ = gate.evaluate(env)
        assert approved is False
        assert reason == "low_confidence"

    def test_at_min_confidence_passes(self, gate):
        env = _make_envelope(confidence=0.3, risk_score=0.3)
        approved, reason, _ = gate.evaluate(env)
        assert reason != "low_confidence"

    def test_above_min_confidence_passes(self, gate):
        env = _make_envelope(confidence=0.5, risk_score=0.3)
        approved, reason, _ = gate.evaluate(env)
        assert reason != "low_confidence"


# ======================================================================
# Rule 4: ENTRY with neutral direction
# ======================================================================

class TestEntryNoDirection:
    def test_entry_neutral_blocked(self, gate):
        env = _make_envelope(
            signal_class=SignalClass.ENTRY,
            direction=SignalDirection.NEUTRAL,
            confidence=0.9,
            risk_score=0.1,
        )
        approved, reason, _ = gate.evaluate(env)
        assert approved is False
        assert reason == "entry_no_direction"

    def test_entry_bullish_passes(self, gate):
        env = _make_envelope(
            signal_class=SignalClass.ENTRY,
            direction=SignalDirection.BULLISH,
            confidence=0.9,
            risk_score=0.1,
        )
        approved, reason, _ = gate.evaluate(env)
        assert approved is True
        assert reason == "passed"

    def test_exit_neutral_not_blocked_by_rule4(self, gate):
        env = _make_envelope(
            signal_class=SignalClass.EXIT,
            direction=SignalDirection.NEUTRAL,
            confidence=0.9,
            risk_score=0.1,
        )
        approved, reason, _ = gate.evaluate(env)
        assert approved is True
        assert reason == "passed"


# ======================================================================
# Pass-through
# ======================================================================

class TestPassThrough:
    def test_clean_signal_passes(self, gate):
        env = _make_envelope(confidence=0.9, risk_score=0.1)
        approved, reason, mod = gate.evaluate(env)
        assert approved is True
        assert reason == "passed"
        assert mod.actionability.can_alert is True

    def test_custom_min_confidence(self):
        gate = RiskGate(min_confidence=0.6)
        env = _make_envelope(confidence=0.5, risk_score=0.1)
        approved, reason, _ = gate.evaluate(env)
        assert approved is False
        assert reason == "low_confidence"


# ======================================================================
# Meta-signals always pass
# ======================================================================

class TestMetaSignalsAlwaysPass:
    @pytest.mark.parametrize("cls", [SignalClass.RISK, SignalClass.SYSTEM_HEALTH, SignalClass.DATA_QUALITY])
    def test_meta_passes_regardless_of_state(self, gate, cls):
        env = _make_envelope(
            signal_class=cls,
            data_quality=DataQuality(status=DataQualityStatus.DEGRADED),
            confidence=0.01,
            risk_score=0.99,
            direction=SignalDirection.NEUTRAL,
        )
        approved, reason, _ = gate.evaluate(env)
        assert approved is True
        assert reason == "passed_meta_signal"


# ======================================================================
# Actionability update
# ======================================================================

class TestActionabilityUpdate:
    def test_approved_can_alert_true(self, gate):
        env = _make_envelope(confidence=0.9, risk_score=0.1)
        _, _, mod = gate.evaluate(env)
        assert mod.actionability.can_alert is True
        assert mod.actionability.can_execute is False
        assert mod.actionability.dry_run_only is True

    def test_rejected_can_alert_false(self, gate):
        env = _make_envelope(confidence=0.1)
        _, _, mod = gate.evaluate(env)
        assert mod.actionability.can_alert is False
        assert mod.actionability.can_execute is False
        assert mod.actionability.dry_run_only is True
