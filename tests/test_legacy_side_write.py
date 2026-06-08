"""Tests for legacy pipeline canonical side-write (Issue #16)."""

from __future__ import annotations

from core.signal_model import Signal
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


def _legacy_signal(**overrides) -> Signal:
    defaults = {
        "pair": "BTC/USDT",
        "action": "BUY",
        "confidence": 75,
        "price": 42000.0,
        "quantity": 0.1,
    }
    defaults.update(overrides)
    return Signal(**defaults)


class TestFromLegacySignal:
    """Test the adapter from legacy Signal to CanonicalSignalEnvelope."""

    def test_basic_conversion(self) -> None:
        sig = _legacy_signal()
        ctx = {"risk_score": 0.4, "feed_health": {"status": "ok"}}
        env = from_legacy_signal(sig, ctx)

        assert isinstance(env, CanonicalSignalEnvelope)
        assert env.asset == "BTC/USDT"
        assert env.signal_class == SignalClass.ENTRY
        assert env.direction == SignalDirection.BULLISH
        assert env.confidence == 0.75
        assert env.risk_score == 0.4
        assert env.data_quality.status == DataQualityStatus.OK

    def test_sell_direction(self) -> None:
        sig = _legacy_signal(action="SELL")
        env = from_legacy_signal(sig)
        assert env.direction == SignalDirection.BEARISH

    def test_hold_direction(self) -> None:
        sig = _legacy_signal(action="HOLD")
        env = from_legacy_signal(sig)
        assert env.direction == SignalDirection.NEUTRAL

    def test_degraded_feed_health(self) -> None:
        sig = _legacy_signal()
        ctx = {"feed_health": {"status": "degraded"}}
        env = from_legacy_signal(sig, ctx)
        assert env.data_quality.status == DataQualityStatus.DEGRADED

    def test_no_context(self) -> None:
        sig = _legacy_signal()
        env = from_legacy_signal(sig)
        assert env.risk_score == 0.5
        assert env.confidence == 0.75


class TestLegacySideWrite:
    """Test that the side-write pipeline produces canonical signals correctly."""

    def test_signal_produces_canonical_envelope(self) -> None:
        sig = _legacy_signal()
        ctx = {"risk_score": 0.3, "feed_health": {"status": "ok"}}
        envelope = from_legacy_signal(sig, ctx)
        gate = RiskGate()
        approved, reason, mod = gate.evaluate(envelope)

        assert approved is True
        assert reason == "passed"
        assert mod.actionability.can_alert is True

    def test_low_confidence_blocked(self) -> None:
        sig = _legacy_signal(confidence=20)
        ctx = {"risk_score": 0.3, "feed_health": {"status": "ok"}}
        envelope = from_legacy_signal(sig, ctx)
        gate = RiskGate()
        approved, reason, mod = gate.evaluate(envelope)

        assert approved is False
        assert reason == "low_confidence"

    def test_stored_in_registry_even_if_blocked(self, tmp_path) -> None:
        registry = CanonicalSignalRegistry(db_path=str(tmp_path / "test.db"))
        gate = RiskGate()

        sig = _legacy_signal(confidence=10)
        envelope = from_legacy_signal(sig)
        approved, reason, mod = gate.evaluate(envelope)

        # Store regardless of approval
        registry.append(mod)

        results = registry.query_latest(asset="BTC/USDT")
        assert len(results) == 1
        assert results[0]["asset"] == "BTC/USDT"
        registry.close()

    def test_data_quality_signal_on_degraded_feed(self) -> None:
        """Simulate the DATA_QUALITY signal emission on unhealthy feed."""
        dq_envelope = CanonicalSignalEnvelope(
            signal_class=SignalClass.DATA_QUALITY,
            subtype="feed_health",
            source="core.market_signals",
            asset="BTC/USDT",
            direction=SignalDirection.NEUTRAL,
            confidence=0.9,
            risk_score=0.3,
            priority=SignalPriority.HIGH,
            reason_codes=["feed_degraded"],
            features={"status": "degraded"},
            data_quality=DataQuality(status=DataQualityStatus.DEGRADED),
            actionability={"can_alert": True},
            invalidation={"max_age_seconds": 3600, "conditions": []},
            raw_refs=[],
        )
        gate = RiskGate()
        approved, reason, mod = gate.evaluate(dq_envelope)

        # DATA_QUALITY always passes (meta signal)
        assert approved is True
        assert reason == "passed_meta_signal"

    def test_full_side_write_pipeline(self, tmp_path) -> None:
        """End-to-end: legacy signal → canonical → risk gate → registry."""

        db_path = str(tmp_path / "canonical.db")
        registry = CanonicalSignalRegistry(db_path=db_path)
        gate = RiskGate()

        # Produce a signal the legacy way
        sig = _legacy_signal(action="BUY", confidence=80)
        ctx = {"risk_score": 0.35, "feed_health": {"status": "ok"}}
        envelope = from_legacy_signal(sig, ctx)

        # Side-write: risk gate + registry
        approved, reason, mod = gate.evaluate(envelope)
        sig_id = registry.append(mod)

        assert approved is True
        assert sig_id is not None

        # Verify stored
        stored = registry.get_signal(sig_id)
        assert stored is not None
        assert stored["asset"] == "BTC/USDT"
        assert stored["signal_class"] == "entry"

        registry.close()
