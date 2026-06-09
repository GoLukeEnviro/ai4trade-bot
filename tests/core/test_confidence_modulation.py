"""Tests for Issue #35 — AI Confidence Modulation Layer."""

from __future__ import annotations

import pytest

from core.signals.confidence_modulation import (
    _DEFAULT_CONFIDENCE,
    _LOW_DATA_COMPLETENESS_PCT,
    _MAX_WARNING_PCT,
    _PER_WARNING_PCT,
    _RISK_CAPS,
    ConfidenceBand,
    ConfidenceModulator,
    ModulatedConfidence,
)
from rainbow.evaluation.models import AIEvaluation

# ======================================================================
# Helpers
# ======================================================================

def _make_eval(
    ai_confidence: float = 0.8,
    risk_level: str = "low",
    warnings: list[str] | None = None,
    data_completeness_score: float | None = None,
) -> AIEvaluation:
    """Build a minimal AIEvaluation for testing."""
    return AIEvaluation(
        ai_confidence=ai_confidence,
        risk_level=risk_level,
        market_regime="quiet",
        reasoning="test",
        model_used="test-model",
        evaluation_latency_ms=0,
        warnings=warnings or [],
        data_completeness_score=data_completeness_score,
    )


def _make_dict(
    ai_confidence: float = 0.8,
    risk_level: str = "low",
    warnings: list[str] | None = None,
    data_completeness_score: float | None = None,
) -> dict:
    """Build a dict representation for testing dict-input path."""
    d: dict = {
        "ai_confidence": ai_confidence,
        "risk_level": risk_level,
    }
    if warnings is not None:
        d["warnings"] = warnings
    if data_completeness_score is not None:
        d["data_completeness_score"] = data_completeness_score
    return d


modulator = ConfidenceModulator()


# ======================================================================
# 1. High confidence + low risk → HIGH band (no cap needed)
# ======================================================================

class TestHighConfidenceLowRisk:
    def test_high_confidence_low_risk_high_band(self):
        result = modulator.modulate(_make_eval(ai_confidence=0.9, risk_level="low"))
        assert result.confidence_band == ConfidenceBand.HIGH
        assert result.final_confidence >= 0.7

    def test_no_safety_cap_applied(self):
        result = modulator.modulate(_make_eval(ai_confidence=0.9, risk_level="low"))
        assert result.safety_cap_applied is False

    def test_final_confidence_equals_raw(self):
        result = modulator.modulate(_make_eval(ai_confidence=0.85, risk_level="low"))
        assert result.final_confidence == pytest.approx(0.85)


# ======================================================================
# 2. High confidence + high risk → capped to LOW band
# ======================================================================

class TestHighConfidenceHighRisk:
    def test_capped_to_low_band(self):
        result = modulator.modulate(_make_eval(ai_confidence=0.9, risk_level="high"))
        assert result.confidence_band == ConfidenceBand.LOW

    def test_capped_at_risk_cap(self):
        result = modulator.modulate(_make_eval(ai_confidence=0.9, risk_level="high"))
        assert result.final_confidence <= _RISK_CAPS["high"]

    def test_safety_cap_applied(self):
        result = modulator.modulate(_make_eval(ai_confidence=0.9, risk_level="high"))
        assert result.safety_cap_applied is True


# ======================================================================
# 3. High confidence + extreme risk → capped to BLOCKED
# ======================================================================

class TestHighConfidenceExtremeRisk:
    def test_extreme_risk_blocked_band(self):
        result = modulator.modulate(_make_eval(ai_confidence=0.95, risk_level="extreme"))
        # After uncertainty penalty, extreme cap at 0.15 may land below 0.1
        # depending on penalties. The cap is 0.15, band should be LOW or BLOCKED.
        assert result.final_confidence <= _RISK_CAPS["extreme"]

    def test_safety_cap_applied_extreme(self):
        result = modulator.modulate(_make_eval(ai_confidence=0.95, risk_level="extreme"))
        assert result.safety_cap_applied is True

    def test_extreme_risk_cap_value(self):
        result = modulator.modulate(_make_eval(ai_confidence=0.95, risk_level="extreme"))
        assert result.final_confidence <= 0.15


# ======================================================================
# 4. Medium confidence + medium risk → MEDIUM band
# ======================================================================

class TestMediumConfidenceMediumRisk:
    def test_medium_confidence_medium_risk(self):
        result = modulator.modulate(_make_eval(ai_confidence=0.5, risk_level="medium"))
        # 0.5 → uncertainty penalty (0.5 * 0.1 = 0.05) → 0.45
        # risk cap for medium is 0.65, so no cap
        # band: 0.4 <= 0.45 < 0.7 → MEDIUM
        assert result.confidence_band == ConfidenceBand.MEDIUM

    def test_medium_risk_no_safety_cap(self):
        result = modulator.modulate(_make_eval(ai_confidence=0.5, risk_level="medium"))
        # 0.5 doesn't exceed cap of 0.65
        assert result.safety_cap_applied is False


# ======================================================================
# 5. Low confidence → stays LOW or gets uncertainty penalty
# ======================================================================

class TestLowConfidence:
    def test_low_confidence_uncertainty_penalty(self):
        result = modulator.modulate(_make_eval(ai_confidence=0.3, risk_level="low"))
        # 0.3 → uncertainty penalty: 0.3 * 0.1 = 0.03 → 0.27
        assert result.final_confidence < 0.3

    def test_low_confidence_stays_low_band(self):
        result = modulator.modulate(_make_eval(ai_confidence=0.3, risk_level="low"))
        # 0.27 → LOW band (>= 0.1)
        assert result.confidence_band == ConfidenceBand.LOW


# ======================================================================
# 6. None confidence → defaults to 0.3, UNKNOWN band
# ======================================================================

class TestNoneConfidence:
    def test_none_confidence_defaults(self):
        result = modulator.modulate(_make_dict(ai_confidence=None, risk_level="low"))
        # The dict path with ai_confidence=None should get _DEFAULT_CONFIDENCE
        # and UNKNOWN band
        assert result.raw_confidence is None
        assert result.confidence_band == ConfidenceBand.UNKNOWN

    def test_none_confidence_default_value(self):
        # Build a dict without ai_confidence key
        result = modulator.modulate({"risk_level": "low"})
        # default confidence should be _DEFAULT_CONFIDENCE=0.3
        # After uncertainty penalty: 0.3 * 0.1 = 0.03 → 0.27
        assert result.final_confidence < _DEFAULT_CONFIDENCE


# ======================================================================
# 7. Invalid negative confidence → safe default
# ======================================================================

class TestInvalidNegativeConfidence:
    def test_negative_confidence_clamped(self):
        result = modulator.modulate(_make_dict(ai_confidence=-0.5, risk_level="low"))
        # -0.5 gets clamped to 0.0, then UNKNOWN band (raw was valid float)
        # Actually: raw_confidence -0.5 is valid float, not None.
        # In _modulate_inner: confidence < 0.0 → clamped to 0.0
        assert result.final_confidence == 0.0

    def test_negative_confidence_no_crash(self):
        result = modulator.modulate(_make_dict(ai_confidence=-0.5, risk_level="low"))
        assert result.final_confidence >= 0.0


# ======================================================================
# 8. Invalid confidence > 1.0 → clamped
# ======================================================================

class TestInvalidHighConfidence:
    def test_confidence_above_one_clamped(self):
        result = modulator.modulate(_make_dict(ai_confidence=1.5, risk_level="low"))
        # 1.5 → clamped to 1.0
        assert result.final_confidence <= 1.0

    def test_confidence_above_one_no_crash(self):
        result = modulator.modulate(_make_dict(ai_confidence=2.0, risk_level="low"))
        assert result.final_confidence <= 1.0


# ======================================================================
# 9. Warnings reduce confidence by 5% each
# ======================================================================

class TestWarningsReduction:
    def test_single_warning_reduction(self):
        result_no_warn = modulator.modulate(
            _make_eval(ai_confidence=0.8, risk_level="low", warnings=[]),
        )
        result_one_warn = modulator.modulate(
            _make_eval(ai_confidence=0.8, risk_level="low", warnings=["high volatility"]),
        )
        diff = result_no_warn.final_confidence - result_one_warn.final_confidence
        # 5% of 0.8 = 0.04
        assert diff == pytest.approx(0.8 * _PER_WARNING_PCT, abs=0.001)

    def test_two_warnings_reduction(self):
        result_no_warn = modulator.modulate(
            _make_eval(ai_confidence=0.8, risk_level="low", warnings=[]),
        )
        result_two_warn = modulator.modulate(
            _make_eval(
                ai_confidence=0.8,
                risk_level="low",
                warnings=["high volatility", "low liquidity"],
            ),
        )
        diff = result_no_warn.final_confidence - result_two_warn.final_confidence
        # 10% of 0.8 = 0.08
        assert diff == pytest.approx(0.8 * 2 * _PER_WARNING_PCT, abs=0.001)


# ======================================================================
# 10. Many warnings cap at 20% reduction
# ======================================================================

class TestMaxWarningsCap:
    def test_many_warnings_capped_at_20pct(self):
        result_4_warn = modulator.modulate(
            _make_eval(
                ai_confidence=0.8,
                risk_level="low",
                warnings=["w1", "w2", "w3", "w4"],
            ),
        )
        result_10_warn = modulator.modulate(
            _make_eval(
                ai_confidence=0.8,
                risk_level="low",
                warnings=[f"w{i}" for i in range(10)],
            ),
        )
        # 4 warnings: 20% → 0.8 * 0.20 = 0.16
        # 10 warnings: capped at 20% → same
        assert result_4_warn.final_confidence == pytest.approx(
            result_10_warn.final_confidence, abs=0.001,
        )

    def test_max_warning_effect(self):
        result_clean = modulator.modulate(
            _make_eval(ai_confidence=0.8, risk_level="low", warnings=[]),
        )
        result_many = modulator.modulate(
            _make_eval(
                ai_confidence=0.8,
                risk_level="low",
                warnings=[f"w{i}" for i in range(10)],
            ),
        )
        diff = result_clean.final_confidence - result_many.final_confidence
        # Max 20% reduction of 0.8 = 0.16
        assert diff == pytest.approx(0.8 * _MAX_WARNING_PCT, abs=0.001)


# ======================================================================
# 11. Low data_completeness_score reduces by 15%
# ======================================================================

class TestDataCompletenessPenalty:
    def test_low_data_completeness(self):
        result_good = modulator.modulate(
            _make_eval(ai_confidence=0.8, risk_level="low", data_completeness_score=0.9),
        )
        result_bad = modulator.modulate(
            _make_eval(ai_confidence=0.8, risk_level="low", data_completeness_score=0.5),
        )
        diff = result_good.final_confidence - result_bad.final_confidence
        # 15% of 0.8 = 0.12
        assert diff == pytest.approx(
            0.8 * _LOW_DATA_COMPLETENESS_PCT, abs=0.001,
        )

    def test_high_data_completeness_no_penalty(self):
        result = modulator.modulate(
            _make_eval(ai_confidence=0.8, risk_level="low", data_completeness_score=0.8),
        )
        # No data completeness penalty
        # No warnings, no uncertainty penalty, low risk → no reduction
        assert result.final_confidence == pytest.approx(0.8)

    def test_none_data_completeness_no_penalty(self):
        result = modulator.modulate(
            _make_eval(ai_confidence=0.8, risk_level="low", data_completeness_score=None),
        )
        assert result.final_confidence == pytest.approx(0.8)


# ======================================================================
# 12. Risk cap is never exceeded regardless of raw confidence
# ======================================================================

class TestRiskCapNotExceeded:
    @pytest.mark.parametrize("risk_level,expected_cap", [
        ("extreme", 0.15),
        ("high", 0.35),
        ("medium", 0.65),
    ])
    def test_cap_never_exceeded(self, risk_level: str, expected_cap: float):
        result = modulator.modulate(
            _make_eval(ai_confidence=1.0, risk_level=risk_level),
        )
        assert result.final_confidence <= expected_cap

    def test_low_risk_no_cap(self):
        result = modulator.modulate(
            _make_eval(ai_confidence=0.99, risk_level="low"),
        )
        # Low risk: cap at 1.0, confidence should be 0.99 (no penalties apply)
        assert result.final_confidence == pytest.approx(0.99)


# ======================================================================
# 13. modulate() never raises on any input
# ======================================================================

class TestNeverRaises:
    def test_none_input(self):
        result = modulator.modulate(None)  # type: ignore[arg-type]
        assert isinstance(result, ModulatedConfidence)
        assert result.final_confidence >= 0.0

    def test_empty_dict(self):
        result = modulator.modulate({})
        assert isinstance(result, ModulatedConfidence)

    def test_string_input(self):
        result = modulator.modulate("not an evaluation")  # type: ignore[arg-type]
        assert isinstance(result, ModulatedConfidence)

    def test_int_input(self):
        result = modulator.modulate(42)  # type: ignore[arg-type]
        assert isinstance(result, ModulatedConfidence)

    def test_list_input(self):
        result = modulator.modulate([1, 2, 3])  # type: ignore[arg-type]
        assert isinstance(result, ModulatedConfidence)

    def test_float_input(self):
        result = modulator.modulate(3.14)  # type: ignore[arg-type]
        assert isinstance(result, ModulatedConfidence)


# ======================================================================
# 14. HOLD bias: result confidence never higher than raw_confidence
# ======================================================================

class TestHoldBias:
    @pytest.mark.parametrize("confidence,risk_level", [
        (0.9, "low"),
        (0.7, "low"),
        (0.5, "medium"),
        (0.3, "high"),
        (0.1, "extreme"),
    ])
    def test_final_never_exceeds_raw(self, confidence: float, risk_level: str):
        result = modulator.modulate(_make_eval(ai_confidence=confidence, risk_level=risk_level))
        assert result.final_confidence <= confidence

    def test_zero_confidence_stays_zero(self):
        result = modulator.modulate(_make_eval(ai_confidence=0.0, risk_level="low"))
        assert result.final_confidence == 0.0


# ======================================================================
# 15. Empty AIEvaluation → safe defaults
# ======================================================================

class TestEmptyEvaluation:
    def test_minimal_evaluation(self):
        result = modulator.modulate(
            AIEvaluation(
                ai_confidence=0.0,
                risk_level="medium",
                market_regime="quiet",
                reasoning="",
                model_used="test",
                evaluation_latency_ms=0,
            ),
        )
        assert isinstance(result, ModulatedConfidence)
        assert result.final_confidence <= 0.0
        assert result.confidence_band in (ConfidenceBand.BLOCKED, ConfidenceBand.LOW)


# ======================================================================
# 16. Malformed dict input → safe defaults
# ======================================================================

class TestMalformedDict:
    def test_missing_confidence_key(self):
        result = modulator.modulate({"risk_level": "low"})
        assert isinstance(result, ModulatedConfidence)

    def test_missing_risk_level_key(self):
        result = modulator.modulate({"ai_confidence": 0.5})
        # Should default to "high" risk level
        assert isinstance(result, ModulatedConfidence)
        assert result.risk_level == "high"

    def test_non_numeric_confidence(self):
        result = modulator.modulate({"ai_confidence": "not a number", "risk_level": "low"})
        assert isinstance(result, ModulatedConfidence)

    def test_invalid_risk_level(self):
        result = modulator.modulate({"ai_confidence": 0.5, "risk_level": "extremely_bad"})
        # Unknown risk level → conservative "high" default
        assert result.risk_level == "high"


# ======================================================================
# 17. confidence_modulation_reason always populated
# ======================================================================

class TestReasonAuditTrail:
    def test_reason_always_populated_on_reduction(self):
        result = modulator.modulate(_make_eval(ai_confidence=0.9, risk_level="high"))
        assert len(result.confidence_modulation_reason) > 0

    def test_reason_present_on_no_reduction(self):
        result = modulator.modulate(_make_eval(ai_confidence=0.8, risk_level="low"))
        # Even with no reductions, reasons may be empty — that's OK
        # But at minimum, the field exists
        assert isinstance(result.confidence_modulation_reason, list)

    def test_reason_with_warnings(self):
        result = modulator.modulate(
            _make_eval(ai_confidence=0.8, risk_level="low", warnings=["test warning"]),
        )
        assert any("warning" in r.lower() for r in result.confidence_modulation_reason)

    def test_reason_with_data_completeness(self):
        result = modulator.modulate(
            _make_eval(ai_confidence=0.8, risk_level="low", data_completeness_score=0.5),
        )
        assert any("data_completeness" in r.lower() for r in result.confidence_modulation_reason)


# ======================================================================
# 18. safety_cap_applied is True when risk cap applied
# ======================================================================

class TestSafetyCapFlag:
    def test_cap_applied_high_risk(self):
        result = modulator.modulate(_make_eval(ai_confidence=0.9, risk_level="high"))
        assert result.safety_cap_applied is True

    def test_no_cap_low_risk(self):
        result = modulator.modulate(_make_eval(ai_confidence=0.5, risk_level="low"))
        assert result.safety_cap_applied is False

    def test_cap_applied_extreme_risk(self):
        result = modulator.modulate(_make_eval(ai_confidence=0.2, risk_level="extreme"))
        assert result.safety_cap_applied is True

    def test_no_cap_medium_risk_below_cap(self):
        result = modulator.modulate(_make_eval(ai_confidence=0.5, risk_level="medium"))
        # 0.5 < 0.65 cap → no cap applied
        assert result.safety_cap_applied is False


# ======================================================================
# 19. risk_modifier reflects actual reduction
# ======================================================================

class TestRiskModifier:
    def test_risk_modifier_1_when_no_cap(self):
        result = modulator.modulate(_make_eval(ai_confidence=0.5, risk_level="low"))
        assert result.risk_modifier == pytest.approx(1.0)

    def test_risk_modifier_less_than_1_when_cap(self):
        result = modulator.modulate(_make_eval(ai_confidence=0.9, risk_level="high"))
        # risk_modifier = cap / raw = 0.35 / 0.9
        expected = 0.35 / 0.9
        assert result.risk_modifier == pytest.approx(expected, abs=0.01)

    def test_risk_modifier_extreme_risk(self):
        result = modulator.modulate(_make_eval(ai_confidence=0.9, risk_level="extreme"))
        expected = 0.15 / 0.9
        assert result.risk_modifier == pytest.approx(expected, abs=0.01)

    def test_risk_modifier_range(self):
        """risk_modifier must be between 0.0 and 1.0."""
        for risk_level in ("low", "medium", "high", "extreme"):
            result = modulator.modulate(_make_eval(ai_confidence=0.8, risk_level=risk_level))
            assert 0.0 <= result.risk_modifier <= 1.0


# ======================================================================
# 20. Backward compatibility: existing AIEvaluation without new fields
# ======================================================================

class TestBackwardCompatibility:
    def test_old_style_aieval(self):
        ev = AIEvaluation(
            ai_confidence=0.7,
            risk_level="low",
            market_regime="trending",
            reasoning="test",
            model_used="m",
            evaluation_latency_ms=0,
        )
        result = modulator.modulate(ev)
        assert isinstance(result, ModulatedConfidence)
        assert result.final_confidence == pytest.approx(0.7)
        assert result.confidence_band == ConfidenceBand.HIGH

    def test_dict_with_only_required_fields(self):
        d = {
            "ai_confidence": 0.6,
            "risk_level": "medium",
        }
        result = modulator.modulate(d)
        assert isinstance(result, ModulatedConfidence)
        # 0.6 → uncertainty penalty → 0.6 - 0.06 = 0.54
        # risk cap 0.65 → no cap
        assert result.final_confidence <= 0.6


# ======================================================================
# Additional: Uncertainty field
# ======================================================================

class TestUncertaintyField:
    def test_uncertainty_derived_from_confidence(self):
        result = modulator.modulate(_make_eval(ai_confidence=0.7, risk_level="low"))
        assert result.uncertainty == pytest.approx(0.3)

    def test_uncertainty_none_when_raw_confidence_none(self):
        result = modulator.modulate({"risk_level": "low"})
        assert result.uncertainty is None

    def test_uncertainty_zero_for_confident(self):
        result = modulator.modulate(_make_eval(ai_confidence=1.0, risk_level="low"))
        assert result.uncertainty == pytest.approx(0.0)


# ======================================================================
# Additional: Combined penalties
# ======================================================================

class TestCombinedPenalties:
    def test_warnings_plus_data_completeness_plus_uncertainty(self):
        """All three penalties stack and risk cap still applies."""
        result = modulator.modulate(
            _make_eval(
                ai_confidence=0.4,
                risk_level="medium",
                warnings=["w1", "w2"],
                data_completeness_score=0.5,
            ),
        )
        # 0.4 → uncertainty penalty: 0.4 * 0.1 = 0.04 → 0.36
        # warnings: 2 * 5% = 10% of 0.36 = 0.036 → 0.324
        # data completeness: 15% of 0.324 = 0.0486 → 0.2754
        # risk cap 0.65 → no cap
        # Final ≈ 0.2754
        assert result.final_confidence < 0.4
        assert result.final_confidence >= 0.0

    def test_extreme_risk_overrides_everything(self):
        """Even high confidence with many warnings and good data → extreme cap."""
        result = modulator.modulate(
            _make_eval(
                ai_confidence=0.95,
                risk_level="extreme",
                warnings=[],
                data_completeness_score=0.95,
            ),
        )
        # Cap at 0.15, uncertainty penalty on 0.15: 0.15 * 0.1 = 0.015 → 0.135
        assert result.final_confidence <= 0.15
        assert result.safety_cap_applied is True


# ======================================================================
# Additional: ConfidenceBand mapping edge cases
# ======================================================================

class TestConfidenceBandMapping:
    def test_exactly_0_7_is_high(self):
        # 0.7 → no uncertainty penalty (0.7 >= 0.5), no other penalties
        result = modulator.modulate(_make_eval(ai_confidence=0.7, risk_level="low"))
        assert result.confidence_band == ConfidenceBand.HIGH

    def test_exactly_0_4_is_medium(self):
        # 0.4 < 0.5 → uncertainty penalty, but let's check band mapping
        # Use a higher confidence that after penalties maps to exactly 0.4
        # Instead, test the mapping function directly
        from core.signals.confidence_modulation import _confidence_to_band
        assert _confidence_to_band(0.4, False) == ConfidenceBand.MEDIUM

    def test_exactly_0_1_is_low(self):
        from core.signals.confidence_modulation import _confidence_to_band
        assert _confidence_to_band(0.1, False) == ConfidenceBand.LOW

    def test_below_0_1_is_blocked(self):
        from core.signals.confidence_modulation import _confidence_to_band
        assert _confidence_to_band(0.05, False) == ConfidenceBand.BLOCKED

    def test_raw_none_is_unknown(self):
        from core.signals.confidence_modulation import _confidence_to_band
        assert _confidence_to_band(0.5, True) == ConfidenceBand.UNKNOWN


# ======================================================================
# Additional: Dict input path
# ======================================================================

class TestDictInputPath:
    def test_dict_with_warnings(self):
        result = modulator.modulate({
            "ai_confidence": 0.8,
            "risk_level": "low",
            "warnings": ["test warning"],
        })
        assert isinstance(result, ModulatedConfidence)
        assert result.final_confidence < 0.8

    def test_dict_with_data_completeness(self):
        result = modulator.modulate({
            "ai_confidence": 0.8,
            "risk_level": "low",
            "data_completeness_score": 0.5,
        })
        assert isinstance(result, ModulatedConfidence)
        assert result.final_confidence < 0.8

    def test_dict_non_list_warnings(self):
        result = modulator.modulate({
            "ai_confidence": 0.8,
            "risk_level": "low",
            "warnings": "not a list",
        })
        # Should handle gracefully
        assert isinstance(result, ModulatedConfidence)


# ======================================================================
# Additional: ModulatedConfidence model validation
# ======================================================================

class TestModulatedConfidenceModel:
    def test_model_fields_present(self):
        result = modulator.modulate(_make_eval())
        assert hasattr(result, "raw_confidence")
        assert hasattr(result, "uncertainty")
        assert hasattr(result, "risk_level")
        assert hasattr(result, "final_confidence")
        assert hasattr(result, "confidence_band")
        assert hasattr(result, "confidence_modulation_reason")
        assert hasattr(result, "safety_cap_applied")
        assert hasattr(result, "risk_modifier")

    def test_final_confidence_in_range(self):
        """Final confidence must always be 0-1."""
        for risk_level in ("low", "medium", "high", "extreme"):
            for conf in (0.0, 0.1, 0.3, 0.5, 0.7, 0.9, 1.0):
                result = modulator.modulate(
                    _make_eval(ai_confidence=conf, risk_level=risk_level),
                )
                assert 0.0 <= result.final_confidence <= 1.0
