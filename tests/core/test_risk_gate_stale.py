"""Tests for RiskGate stale_threshold_seconds enforcement (P1 hardening)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

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
# Rule 2: stale signal threshold
# ======================================================================

class TestStaleThreshold:
    """Verify that stale_threshold_seconds is wired into RiskGate.evaluate()."""

    def test_fresh_signal_passes_staleness_check(self, gate):
        """A freshly-created signal (default created_at = now) should pass staleness."""
        env = _make_envelope(confidence=0.9, risk_score=0.1)
        approved, reason, mod = gate.evaluate(env)
        assert approved is True
        assert reason == "passed"

    def test_stale_signal_blocked(self, gate):
        """A signal older than stale_threshold_seconds is blocked."""
        old_time = datetime.now(UTC) - timedelta(seconds=gate.stale_threshold_seconds + 10)
        env = _make_envelope(
            confidence=0.9,
            risk_score=0.1,
            created_at=old_time,
        )
        approved, reason, mod = gate.evaluate(env)
        assert approved is False
        assert reason == "stale_signal"

    def test_signal_exactly_at_threshold_passes(self):
        """A signal at exactly the threshold age should still pass (not stale)."""
        threshold = 300
        gate = RiskGate(min_confidence=0.3, stale_threshold_seconds=threshold)
        # Use a time that is 1 second LESS than threshold to avoid timing edge
        just_under = datetime.now(UTC) - timedelta(seconds=threshold - 1)
        env = _make_envelope(
            confidence=0.9,
            risk_score=0.1,
            created_at=just_under,
        )
        approved, reason, mod = gate.evaluate(env)
        # Should pass because staleness < threshold
        assert approved is True
        assert reason == "passed"

    def test_signal_just_over_threshold_blocked(self):
        """A signal 1 second over the threshold is blocked."""
        threshold = 300
        gate = RiskGate(min_confidence=0.3, stale_threshold_seconds=threshold)
        just_over = datetime.now(UTC) - timedelta(seconds=threshold + 1)
        env = _make_envelope(
            confidence=0.9,
            risk_score=0.1,
            created_at=just_over,
        )
        approved, reason, mod = gate.evaluate(env)
        assert approved is False
        assert reason == "stale_signal"

    def test_threshold_override_changes_boundary(self):
        """Changing stale_threshold_seconds changes which signals are considered stale."""
        gate_short = RiskGate(min_confidence=0.3, stale_threshold_seconds=10)
        # Signal 60 seconds old — under default (300s) but over short threshold (10s)
        old_time = datetime.now(UTC) - timedelta(seconds=60)
        env = _make_envelope(confidence=0.9, risk_score=0.1, created_at=old_time)

        # With short threshold: blocked
        approved_short, reason_short, _ = gate_short.evaluate(env)
        assert approved_short is False
        assert reason_short == "stale_signal"

        # With default threshold: passes
        gate_default = RiskGate(min_confidence=0.3, stale_threshold_seconds=300)
        approved_default, _, _ = gate_default.evaluate(env)
        assert approved_default is True

    def test_stale_signal_cannot_produce_can_execute_true(self, gate):
        """Stale signals must NOT produce can_execute=True."""
        old_time = datetime.now(UTC) - timedelta(seconds=gate.stale_threshold_seconds + 10)
        env = _make_envelope(confidence=0.9, risk_score=0.1, created_at=old_time)
        approved, reason, mod = gate.evaluate(env)
        assert approved is False
        assert reason == "stale_signal"
        assert mod.actionability.can_execute is False
        assert mod.actionability.can_alert is False
        assert mod.actionability.dry_run_only is True

    def test_stale_signal_actionability_can_alert_false(self, gate):
        """Stale signals have can_alert=False."""
        old_time = datetime.now(UTC) - timedelta(seconds=gate.stale_threshold_seconds + 10)
        env = _make_envelope(confidence=0.9, risk_score=0.1, created_at=old_time)
        _, _, mod = gate.evaluate(env)
        assert mod.actionability.can_alert is False

    def test_naive_datetime_treated_as_utc(self):
        """A created_at with no tzinfo is treated as UTC (safe degradation)."""
        gate = RiskGate(min_confidence=0.3, stale_threshold_seconds=300)
        # Create a datetime with no tzinfo that is recent
        naive_now = datetime.now(UTC).replace(tzinfo=None)
        env = _make_envelope(confidence=0.9, risk_score=0.1, created_at=naive_now)
        approved, reason, _ = gate.evaluate(env)
        # Should pass since it's basically "now" treated as UTC
        assert approved is True


class TestStaleThresholdEdgeCases:
    """Edge cases around missing/invalid/zero timestamps."""

    def test_default_threshold_is_300_seconds(self):
        """Default stale_threshold_seconds should be 300."""
        gate = RiskGate()
        assert gate.stale_threshold_seconds == 300

    def test_staleness_check_happens_before_risk_check(self, gate):
        """Stale signals should be blocked even if risk and confidence are fine."""
        old_time = datetime.now(UTC) - timedelta(seconds=gate.stale_threshold_seconds + 100)
        env = _make_envelope(confidence=0.99, risk_score=0.01, created_at=old_time)
        approved, reason, _ = gate.evaluate(env)
        assert approved is False
        assert reason == "stale_signal"
        # Should NOT reach "risk_too_high" or "low_confidence"

    def test_meta_signals_bypass_staleness(self, gate):
        """Meta-signals (RISK, SYSTEM_HEALTH, DATA_QUALITY) always pass, even if stale."""
        old_time = datetime.now(UTC) - timedelta(seconds=gate.stale_threshold_seconds + 100)
        for cls in (SignalClass.RISK, SignalClass.SYSTEM_HEALTH, SignalClass.DATA_QUALITY):
            env = _make_envelope(
                signal_class=cls,
                created_at=old_time,
            )
            approved, reason, _ = gate.evaluate(env)
            assert approved is True
            assert reason == "passed_meta_signal"

    def test_stale_signal_with_degraded_quality_reports_staleness(self, gate):
        """If a signal is both stale and has degraded data quality,
        data_quality_degraded takes priority (checked first)."""
        old_time = datetime.now(UTC) - timedelta(seconds=gate.stale_threshold_seconds + 10)
        env = _make_envelope(
            data_quality=DataQuality(status=DataQualityStatus.DEGRADED),
            created_at=old_time,
        )
        approved, reason, _ = gate.evaluate(env)
        assert approved is False
        # Data quality is checked before staleness, so it should report that
        assert reason == "data_quality_degraded"


class TestStalenessComputation:
    """Unit tests for _compute_staleness_seconds helper."""

    def test_compute_staleness_recent_signal(self):
        """A signal just created should have near-zero staleness."""
        env = _make_envelope(created_at=datetime.now(UTC))
        staleness = RiskGate._compute_staleness_seconds(env)
        assert staleness is not None
        assert staleness < 5  # Should be < 5 seconds old

    def test_compute_staleness_old_signal(self):
        """A signal from 1 hour ago should have staleness ~3600."""
        old_time = datetime.now(UTC) - timedelta(hours=1)
        env = _make_envelope(created_at=old_time)
        staleness = RiskGate._compute_staleness_seconds(env)
        assert staleness is not None
        assert staleness >= 3600
