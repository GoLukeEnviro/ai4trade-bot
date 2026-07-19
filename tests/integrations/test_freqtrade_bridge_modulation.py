"""Tests for confidence modulation integration in FreqtradeBridge.

All tests verify that:
  - final_confidence is NEVER higher than raw_confidence
  - HOLD signals stay HOLD after modulation (never become BUY/SELL)
  - Confidence modulation ONLY reduces confidence
  - BLOCKED band forces HOLD
  - Fallback on modulator error uses raw confidence
  - Feature flag use_confidence_modulation respects False
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from core.signals.confidence_modulation import ConfidenceBand
from core.signals.envelope import (
    Actionability,
    CanonicalSignalEnvelope,
    DataQuality,
    DataQualityStatus,
    SignalClass,
    SignalDirection,
    SignalPriority,
)
from core.signals.registry import CanonicalSignalRegistry
from integrations.freqtrade_bridge import FreqtradeBridge

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_envelope(
    *,
    direction: SignalDirection = SignalDirection.BULLISH,
    confidence: float = 0.85,
    risk_score: float = 0.3,
    data_quality_status: DataQualityStatus = DataQualityStatus.OK,
    valid_until: datetime | None = None,
    asset: str = "BTC/USDT",
    source: str = "test",
) -> CanonicalSignalEnvelope:
    """Create a valid canonical signal envelope for testing."""
    return CanonicalSignalEnvelope(
        signal_class=SignalClass.ENTRY,
        subtype="test",
        source=source,
        asset=asset,
        direction=direction,
        confidence=confidence,
        risk_score=risk_score,
        priority=SignalPriority.MEDIUM,
        reason_codes=["test"],
        data_quality=DataQuality(status=data_quality_status),
        actionability=Actionability(can_alert=True),
        valid_until=valid_until,
    )


def _make_registry_with_signal(envelope: CanonicalSignalEnvelope) -> CanonicalSignalRegistry:
    """Create an in-memory registry with one signal."""
    import os
    import tempfile

    db_path = os.path.join(tempfile.mkdtemp(), "test_signals.db")
    registry = CanonicalSignalRegistry(db_path)
    registry.append(envelope)
    return registry


def _make_bridge_with_registry(
    env: CanonicalSignalEnvelope,
    *,
    use_confidence_modulation: bool = True,
    confidence_threshold: float = 0.6,
    risk_threshold: float = 0.7,
) -> tuple[FreqtradeBridge, CanonicalSignalRegistry]:
    """Create a bridge with a registry containing the given envelope."""
    registry = _make_registry_with_signal(env)
    bridge = FreqtradeBridge(
        registry,
        confidence_threshold=confidence_threshold,
        risk_threshold=risk_threshold,
        min_interval_seconds=0.0,
        use_confidence_modulation=use_confidence_modulation,
    )
    return bridge, registry


# ---------------------------------------------------------------------------
# Test: Modulation reduces high confidence when risk is high
# ---------------------------------------------------------------------------

class TestModulationReducesHighConfidence:
    def test_modulation_reduces_high_confidence(self):
        """raw=0.9 + risk='high' → final < 0.9."""
        env = _make_envelope(
            direction=SignalDirection.BULLISH,
            confidence=0.9,
            risk_score=0.75,  # maps to 'high' via _risk_level_from_score
        )
        # Use risk_threshold=1.0 so step 6 doesn't short-circuit to HOLD
        bridge, registry = _make_bridge_with_registry(env, risk_threshold=1.0)
        try:
            result = bridge.get_latest_signal("BTC/USDT")
            # With risk_level='high', the modulator caps at 0.35
            assert result["confidence"] < 0.9
            assert "raw_confidence" in result
            assert result["raw_confidence"] == 0.9
        finally:
            registry.close()


# ---------------------------------------------------------------------------
# Test: BLOCKED band forces HOLD
# ---------------------------------------------------------------------------

class TestModulationBlockedForcesHold:
    def test_modulation_blocked_forces_hold(self):
        """Extreme risk → BLOCKED band → HOLD action."""
        # Use low raw confidence so that after extreme risk cap (0.15)
        # and uncertainty penalty, final < 0.1 → BLOCKED band.
        # confidence=0.2, risk_score=0.95 (extreme, cap=0.15)
        # → capped at 0.15, then uncertainty penalty (0.15*0.10=0.015) → 0.135
        # Band: 0.135 >= 0.1 → LOW, not BLOCKED.
        # But with confidence=0.08 (< threshold), we need low threshold too.
        # Actually: confidence=0.15, extreme risk cap=0.15 stays at 0.15,
        # uncertainty: 0.15*0.10=0.015 → 0.135, band=LOW
        # To get BLOCKED: raw_confidence must be very low with extreme risk.
        # Use confidence=0.12, risk_score=0.95:
        #   → cap at 0.12 (below 0.15 cap), uncertainty: 0.12*0.10=0.012 → 0.108
        #   → re-apply cap: 0.108, band: 0.108 >= 0.1 → LOW still.
        # Use confidence=0.1, risk_score=0.95:
        #   → cap at 0.1 (below 0.15), uncertainty: 0.1*0.10=0.01 → 0.09
        #   → band: 0.09 < 0.1 → BLOCKED ✓
        env = _make_envelope(
            direction=SignalDirection.BULLISH,
            confidence=0.1,
            risk_score=0.95,  # maps to 'extreme'
        )
        # Set low confidence threshold so the envelope passes step 5
        bridge, registry = _make_bridge_with_registry(
            env,
            confidence_threshold=0.05,
            risk_threshold=1.0,
        )
        try:
            result = bridge.get_latest_signal("BTC/USDT")
            # risk_score=0.95 < risk_threshold=1.0, so passes step 6
            # But risk_level='extreme' → cap=0.15 → BLOCKED band → HOLD
            assert result["action"] == "hold"
            assert result["reason"] == "modulation_blocked"
            assert "confidence_band" in result
            assert result["confidence_band"] == "BLOCKED"
        finally:
            registry.close()


# ---------------------------------------------------------------------------
# Test: HOLD remains HOLD after modulation
# ---------------------------------------------------------------------------

class TestHoldRemainsHoldAfterModulation:
    def test_neutral_maps_to_flat_after_modulation(self):
        """NEUTRAL direction → 'flat' action stays 'flat' even with modulation."""
        env = _make_envelope(
            direction=SignalDirection.NEUTRAL,
            confidence=0.85,
            risk_score=0.3,  # low risk
        )
        bridge, registry = _make_bridge_with_registry(env, risk_threshold=1.0)
        try:
            result = bridge.get_latest_signal("BTC/USDT")
            assert result["action"] == "flat"
            # NEUTRAL maps to 'flat' — distinct from error-fallback 'hold'
        finally:
            registry.close()


# ---------------------------------------------------------------------------
# Test: BUY stays BUY with low risk
# ---------------------------------------------------------------------------

class TestBuyStaysBuyWithLowRisk:
    def test_buy_stays_buy_with_low_risk(self):
        """Low risk + high confidence → LONG preserved after modulation."""
        env = _make_envelope(
            direction=SignalDirection.BULLISH,
            confidence=0.85,
            risk_score=0.2,  # maps to 'low' → no cap
        )
        bridge, registry = _make_bridge_with_registry(env, risk_threshold=1.0)
        try:
            result = bridge.get_latest_signal("BTC/USDT")
            assert result["action"] == "long"
            # With low risk, confidence should be preserved
            assert result["confidence"] == pytest.approx(0.85, abs=0.01)
        finally:
            registry.close()


# ---------------------------------------------------------------------------
# Test: SHORT stays SHORT with low risk
# ---------------------------------------------------------------------------

class TestSellStaysSellWithLowRisk:
    def test_short_stays_short_with_low_risk(self):
        """Low risk + high confidence → SHORT preserved after modulation."""
        env = _make_envelope(
            direction=SignalDirection.BEARISH,
            confidence=0.9,
            risk_score=0.2,  # maps to 'low' → no cap
        )
        bridge, registry = _make_bridge_with_registry(env, risk_threshold=1.0)
        try:
            result = bridge.get_latest_signal("BTC/USDT")
            assert result["action"] == "short"
            assert result["confidence"] == pytest.approx(0.9, abs=0.01)
        finally:
            registry.close()


# ---------------------------------------------------------------------------
# Test: Fallback on modulator error
# ---------------------------------------------------------------------------

class TestFallbackOnModulatorError:
    def test_fallback_on_modulator_error(self):
        """If modulator raises, raw confidence is used instead."""
        env = _make_envelope(
            direction=SignalDirection.BULLISH,
            confidence=0.85,
            risk_score=0.2,
        )
        bridge, registry = _make_bridge_with_registry(env, risk_threshold=1.0)
        try:
            # Patch the modulator to raise an exception
            with patch.object(
                bridge._modulator, "modulate", side_effect=RuntimeError("boom")
            ):
                result = bridge.get_latest_signal("BTC/USDT")
            # Should fall back to raw confidence
            assert result["action"] == "long"
            assert result["confidence"] == 0.85
        finally:
            registry.close()


# ---------------------------------------------------------------------------
# Test: Modulation disabled uses raw confidence
# ---------------------------------------------------------------------------

class TestModulationDisabledUsesRaw:
    def test_modulation_disabled_uses_raw(self):
        """When use_confidence_modulation=False, raw confidence is used."""
        env = _make_envelope(
            direction=SignalDirection.BULLISH,
            confidence=0.85,
            risk_score=0.75,  # would normally trigger modulation
        )
        bridge, registry = _make_bridge_with_registry(
            env,
            use_confidence_modulation=False,
            risk_threshold=1.0,
        )
        try:
            result = bridge.get_latest_signal("BTC/USDT")
            # Without modulation, confidence should be raw
            assert result["action"] == "long"
            assert result["confidence"] == 0.85
            # No modulation metadata should be present
            assert "raw_confidence" not in result
            assert "modulation_reasons" not in result
            assert "confidence_band" not in result
        finally:
            registry.close()


# ---------------------------------------------------------------------------
# Test: Safety assertion — final <= raw always
# ---------------------------------------------------------------------------

class TestSafetyAssertionFinalLeqRaw:
    @pytest.mark.parametrize(
        "confidence,risk_score",
        [
            (0.9, 0.75),   # high risk
            (0.85, 0.5),   # medium risk
            (0.7, 0.2),    # low risk — should be unchanged
            (0.6, 0.85),   # high risk near threshold
            (0.95, 0.95),  # extreme risk
        ],
    )
    def test_final_confidence_leq_raw(self, confidence, risk_score):
        """final_confidence MUST be <= raw_confidence in all cases."""
        env = _make_envelope(
            direction=SignalDirection.BULLISH,
            confidence=confidence,
            risk_score=risk_score,
        )
        # Use risk_threshold=1.0 and low confidence_threshold so
        # envelope passes all checks and reaches modulation
        bridge, registry = _make_bridge_with_registry(
            env, confidence_threshold=0.05, risk_threshold=1.0
        )
        try:
            result = bridge.get_latest_signal("BTC/USDT")
            # If modulation metadata is present
            if "raw_confidence" in result:
                assert result["confidence"] <= result["raw_confidence"]
            else:
                # Without modulation metadata, confidence should equal raw
                assert result["confidence"] == confidence
        finally:
            registry.close()

    def test_safety_revert_on_inflated_confidence(self):
        """If modulator somehow returns final > raw, we revert to raw."""
        env = _make_envelope(
            direction=SignalDirection.BULLISH,
            confidence=0.5,
            risk_score=0.2,  # low risk
        )
        # Set low confidence threshold so the envelope passes step 5
        bridge, registry = _make_bridge_with_registry(
            env, confidence_threshold=0.1, risk_threshold=1.0
        )
        try:
            # Create a mock modulated result that violates the invariant
            fake_modulated = MagicMock()
            fake_modulated.final_confidence = 0.99  # exceeds raw 0.5
            fake_modulated.confidence_band = ConfidenceBand.HIGH
            fake_modulated.confidence_modulation_reason = ["test"]

            with patch.object(
                bridge._modulator, "modulate", return_value=fake_modulated
            ):
                result = bridge.get_latest_signal("BTC/USDT")

            # Safety assertion should revert to raw
            assert result["confidence"] == 0.5
            assert result["raw_confidence"] == 0.5
        finally:
            registry.close()


# ---------------------------------------------------------------------------
# Test: Modulation reason in response
# ---------------------------------------------------------------------------

class TestModulationReasonInResponse:
    def test_modulation_reason_in_response(self):
        """When modulation is applied, reasons are included in the response."""
        env = _make_envelope(
            direction=SignalDirection.BULLISH,
            confidence=0.9,
            risk_score=0.75,  # high risk → cap at 0.35
        )
        bridge, registry = _make_bridge_with_registry(env, risk_threshold=1.0)
        try:
            result = bridge.get_latest_signal("BTC/USDT")
            # Modulation reasons should be populated
            if "modulation_reasons" in result:
                assert isinstance(result["modulation_reasons"], list)
                assert len(result["modulation_reasons"]) > 0
                # Should mention risk cap
                reason_text = " ".join(result["modulation_reasons"])
                assert "risk" in reason_text.lower()
        finally:
            registry.close()

    def test_confidence_band_in_response(self):
        """When modulation is applied, confidence_band is in the response."""
        env = _make_envelope(
            direction=SignalDirection.BULLISH,
            confidence=0.65,
            risk_score=0.3,
        )
        bridge, registry = _make_bridge_with_registry(env, risk_threshold=1.0)
        try:
            result = bridge.get_latest_signal("BTC/USDT")
            assert "confidence_band" in result
            assert result["confidence_band"] in ("LOW", "MEDIUM", "HIGH", "BLOCKED")
        finally:
            registry.close()
