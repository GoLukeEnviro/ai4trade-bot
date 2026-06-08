"""Tests for Issue #13 — Canonical Signal Envelope and Adapter Contracts."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.signal_model import Signal
from core.signals.adapters import from_legacy_signal, from_rainbow_signal
from core.signals.envelope import (
    Actionability,
    CanonicalSignalEnvelope,
    DataQuality,
    DataQualityStatus,
    InvalidationRule,
    SignalClass,
    SignalDirection,
    SignalPriority,
)

# ======================================================================
# Helpers
# ======================================================================

def _make_envelope(**overrides) -> CanonicalSignalEnvelope:
    """Build a valid envelope with sensible defaults, overriding *overrides*."""
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
        features={"foo": 1},
        data_quality=DataQuality(status=DataQualityStatus.OK),
        actionability=Actionability(can_alert=True),
        invalidation=InvalidationRule(),
        raw_refs=[],
    )
    defaults.update(overrides)
    return CanonicalSignalEnvelope(**defaults)


# ======================================================================
# Envelope creation and validation
# ======================================================================

class TestEnvelopeCreation:
    def test_basic_creation(self):
        env = _make_envelope()
        assert env.schema_version == 1
        assert env.signal_class == SignalClass.ENTRY
        assert env.asset == "BTC/USDT"
        assert env.direction == SignalDirection.BULLISH

    def test_auto_generates_uuid(self):
        env = _make_envelope()
        assert len(env.id) == 36  # standard UUID length

    def test_auto_generates_timestamp(self):
        env = _make_envelope()
        assert env.created_at is not None

    def test_all_signal_classes(self):
        for cls in SignalClass:
            env = _make_envelope(signal_class=cls)
            assert env.signal_class == cls

    def test_all_directions(self):
        for d in SignalDirection:
            env = _make_envelope(direction=d)
            assert env.direction == d

    def test_all_priorities(self):
        for p in SignalPriority:
            env = _make_envelope(priority=p)
            assert env.priority == p

    def test_reason_codes_empty_is_valid(self):
        env = _make_envelope(reason_codes=[])
        assert env.reason_codes == []

    def test_features_default_empty_dict(self):
        env = _make_envelope(features={})
        assert env.features == {}

    def test_raw_refs_default_empty(self):
        env = _make_envelope(raw_refs=[])
        assert env.raw_refs == []

    def test_timeframe_optional(self):
        env = _make_envelope(timeframe=None)
        assert env.timeframe is None
        env2 = _make_envelope(timeframe="1h")
        assert env2.timeframe == "1h"

    def test_valid_until_optional(self):
        env = _make_envelope(valid_until=None)
        assert env.valid_until is None


# ======================================================================
# Safety invariants
# ======================================================================

class TestSafetyInvariants:
    def test_dry_run_only_always_true(self):
        action = Actionability(can_alert=True, dry_run_only=False)
        assert action.dry_run_only is True

    def test_dry_run_only_enforced_even_if_set_true(self):
        action = Actionability(can_alert=True, dry_run_only=True)
        assert action.dry_run_only is True

    def test_can_execute_always_false(self):
        action = Actionability(can_alert=True, can_execute=True)
        assert action.can_execute is False

    def test_can_execute_enforced_even_if_set_false(self):
        action = Actionability(can_alert=True, can_execute=False)
        assert action.can_execute is False

    def test_envelope_actionability_inherits_safety(self):
        env = _make_envelope(actionability=Actionability(can_alert=True, can_execute=True, dry_run_only=False))
        assert env.actionability.can_execute is False
        assert env.actionability.dry_run_only is True


# ======================================================================
# Validation
# ======================================================================

class TestValidation:
    def test_confidence_out_of_range_high(self):
        with pytest.raises(ValidationError):
            _make_envelope(confidence=1.5)

    def test_confidence_out_of_range_negative(self):
        with pytest.raises(ValidationError):
            _make_envelope(confidence=-0.1)

    def test_confidence_boundary_zero(self):
        env = _make_envelope(confidence=0.0)
        assert env.confidence == 0.0

    def test_confidence_boundary_one(self):
        env = _make_envelope(confidence=1.0)
        assert env.confidence == 1.0

    def test_risk_score_out_of_range(self):
        with pytest.raises(ValidationError):
            _make_envelope(risk_score=2.0)

    def test_risk_score_negative(self):
        with pytest.raises(ValidationError):
            _make_envelope(risk_score=-0.5)

    def test_confidence_and_risk_are_separate(self):
        env = _make_envelope(confidence=0.9, risk_score=0.1)
        assert env.confidence != env.risk_score

    def test_invalid_signal_class_rejected(self):
        with pytest.raises(ValidationError):
            _make_envelope(signal_class="not_a_class")

    def test_invalid_direction_rejected(self):
        with pytest.raises(ValidationError):
            _make_envelope(direction="sideways")


# ======================================================================
# Adapter: from_legacy_signal
# ======================================================================

class TestFromLegacySignal:
    def _make_legacy(self, **kw) -> Signal:
        defaults = dict(pair="ETH/USDT", action="BUY", confidence=80, price=2000.0, quantity=1.0)
        defaults.update(kw)
        return Signal(**defaults)

    def test_basic_conversion(self):
        sig = self._make_legacy()
        env = from_legacy_signal(sig)
        assert env.asset == "ETH/USDT"
        assert env.signal_class == SignalClass.ENTRY
        assert env.direction == SignalDirection.BULLISH
        assert env.confidence == pytest.approx(0.8)
        assert env.source == "core.signal_model"

    def test_sell_direction(self):
        sig = self._make_legacy(action="SELL")
        env = from_legacy_signal(sig)
        assert env.direction == SignalDirection.BEARISH

    def test_hold_direction(self):
        sig = self._make_legacy(action="HOLD")
        env = from_legacy_signal(sig)
        assert env.direction == SignalDirection.NEUTRAL

    def test_confidence_scaled(self):
        sig = self._make_legacy(confidence=50)
        env = from_legacy_signal(sig)
        assert env.confidence == pytest.approx(0.5)

    def test_market_context_risk_score(self):
        sig = self._make_legacy()
        env = from_legacy_signal(sig, market_context={"risk_score": 0.7})
        assert env.risk_score == pytest.approx(0.7)

    def test_default_risk_score(self):
        sig = self._make_legacy()
        env = from_legacy_signal(sig)
        assert env.risk_score == pytest.approx(0.5)

    def test_feed_health_ok(self):
        sig = self._make_legacy()
        env = from_legacy_signal(sig, market_context={"feed_health": {"status": "ok"}})
        assert env.data_quality.status == DataQualityStatus.OK

    def test_feed_health_degraded(self):
        sig = self._make_legacy()
        env = from_legacy_signal(sig, market_context={"feed_health": {"status": "degraded"}})
        assert env.data_quality.status == DataQualityStatus.DEGRADED

    def test_safety_invariants_preserved(self):
        sig = self._make_legacy()
        env = from_legacy_signal(sig)
        assert env.actionability.can_execute is False
        assert env.actionability.dry_run_only is True

    def test_subtype_is_legacy(self):
        sig = self._make_legacy()
        env = from_legacy_signal(sig)
        assert env.subtype == "legacy"


# ======================================================================
# Adapter: from_rainbow_signal
# ======================================================================

class TestFromRainbowSignal:
    def _make_rainbow(self, **kw):
        from rainbow.models.signal import CryptoSignal, Direction, SignalType

        defaults = dict(
            source="test-collector",
            asset="SOL/USDT",
            signal_type=SignalType.TECHNICAL,
            direction=Direction.BULLISH,
            strength=0.85,
            confidence=0.9,
            metadata={"indicator": "rsi"},
        )
        defaults.update(kw)
        return CryptoSignal(**defaults)

    def test_basic_conversion(self):
        sig = self._make_rainbow()
        env = from_rainbow_signal(sig)
        assert env.asset == "SOL/USDT"
        assert env.direction == SignalDirection.BULLISH
        assert env.confidence == pytest.approx(0.85)
        assert env.source.startswith("rainbow:")

    def test_bearish_direction(self):
        from rainbow.models.signal import Direction
        sig = self._make_rainbow(direction=Direction.BEARISH)
        env = from_rainbow_signal(sig)
        assert env.direction == SignalDirection.BEARISH

    def test_neutral_direction(self):
        from rainbow.models.signal import Direction
        sig = self._make_rainbow(direction=Direction.NEUTRAL)
        env = from_rainbow_signal(sig)
        assert env.direction == SignalDirection.NEUTRAL

    def test_none_direction_defaults_neutral(self):
        sig = self._make_rainbow(direction=None)
        env = from_rainbow_signal(sig)
        assert env.direction == SignalDirection.NEUTRAL

    def test_risk_score_parameter(self):
        sig = self._make_rainbow()
        env = from_rainbow_signal(sig, risk_score=0.65)
        assert env.risk_score == pytest.approx(0.65)

    def test_default_risk_score(self):
        sig = self._make_rainbow()
        env = from_rainbow_signal(sig)
        assert env.risk_score == pytest.approx(0.5)

    def test_signal_id_in_raw_refs(self):
        sig = self._make_rainbow()
        env = from_rainbow_signal(sig)
        assert sig.signal_id in env.raw_refs

    def test_metadata_in_features(self):
        sig = self._make_rainbow()
        env = from_rainbow_signal(sig)
        assert env.features.get("indicator") == "rsi"

    def test_safety_invariants_preserved(self):
        sig = self._make_rainbow()
        env = from_rainbow_signal(sig)
        assert env.actionability.can_execute is False
        assert env.actionability.dry_run_only is True

    def test_macro_maps_to_regime(self):
        from rainbow.models.signal import SignalType
        sig = self._make_rainbow(signal_type=SignalType.MACRO)
        env = from_rainbow_signal(sig)
        assert env.signal_class == SignalClass.REGIME
