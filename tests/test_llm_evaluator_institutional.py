"""Tests for Issue #34 — Institutional-grade LLM Evaluator Upgrade."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from rainbow.evaluation.llm_evaluator import (
    SYSTEM_PROMPT,
    LLMEvaluator,
    _extract_optional_float,
    _extract_optional_list,
    _extract_optional_str,
    _safe_default_evaluation,
)
from rainbow.evaluation.models import AIEvaluation
from rainbow.models.signal import CryptoSignal, Direction, SignalType

# ======================================================================
# Helpers
# ======================================================================

def _make_signal(
    rainbow_score: float = 0.8,
    direction: Direction = Direction.BULLISH,
    asset: str = "BTC",
) -> CryptoSignal:
    return CryptoSignal(
        source="test",
        asset=asset,
        signal_type=SignalType.TECHNICAL,
        direction=direction,
        strength=0.75,
        confidence=0.8,
        rainbow_score=rainbow_score,
        raw_data={"rsi": 62, "macd": 0.003},
        timestamp=datetime.now(UTC),
    )


def _mock_response(payload: dict) -> MagicMock:
    msg = MagicMock()
    msg.content = json.dumps(payload)
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _mock_raw_response(content: str) -> MagicMock:
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


@pytest.fixture
def evaluator(monkeypatch: pytest.MonkeyPatch) -> LLMEvaluator:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    return LLMEvaluator(threshold=0.5)


# ======================================================================
# 3a: SYSTEM_PROMPT directives
# ======================================================================

class TestSystemPromptDirectives:
    """Verify the institutional-grade directives are present in SYSTEM_PROMPT."""

    def test_prompt_contains_capital_preservation(self):
        assert "capital preservation" in SYSTEM_PROMPT.lower()

    def test_prompt_contains_anti_hallucination(self):
        assert "never fabricate" in SYSTEM_PROMPT.lower()

    def test_prompt_contains_data_quality_caution(self):
        assert "incomplete" in SYSTEM_PROMPT.lower() or "flag it" in SYSTEM_PROMPT.lower()

    def test_prompt_contains_leverage_caution(self):
        assert "leverage" in SYSTEM_PROMPT.lower()

    def test_prompt_contains_position_sizing_caution(self):
        assert "position" in SYSTEM_PROMPT.lower() or "sizing" in SYSTEM_PROMPT.lower()

    def test_prompt_contains_advisory_only_rule(self):
        assert "advisory only" in SYSTEM_PROMPT.lower()

    def test_prompt_contains_no_execution_rule(self):
        assert "do not recommend direct order execution" in SYSTEM_PROMPT.lower()

    def test_prompt_contains_uncertainty_hold_rule(self):
        assert "prefer hold" in SYSTEM_PROMPT.lower() or "lower confidence" in SYSTEM_PROMPT.lower()


# ======================================================================
# 3b: AIEvaluation new fields — schema
# ======================================================================

class TestAIEvaluationNewFieldsSchema:
    """Test the new institutional-grade fields on AIEvaluation."""

    def test_recommended_action_none_by_default(self):
        ev = AIEvaluation(
            ai_confidence=0.5,
            risk_level="medium",
            market_regime="quiet",
            reasoning="test",
            model_used="m",
            evaluation_latency_ms=0,
        )
        assert ev.recommended_action is None

    def test_suggested_position_size_pct_none_by_default(self):
        ev = AIEvaluation(
            ai_confidence=0.5,
            risk_level="medium",
            market_regime="quiet",
            reasoning="test",
            model_used="m",
            evaluation_latency_ms=0,
        )
        assert ev.suggested_position_size_pct is None

    def test_suggested_leverage_none_by_default(self):
        ev = AIEvaluation(
            ai_confidence=0.5,
            risk_level="medium",
            market_regime="quiet",
            reasoning="test",
            model_used="m",
            evaluation_latency_ms=0,
        )
        assert ev.suggested_leverage is None

    def test_warnings_default_empty_list(self):
        ev = AIEvaluation(
            ai_confidence=0.5,
            risk_level="medium",
            market_regime="quiet",
            reasoning="test",
            model_used="m",
            evaluation_latency_ms=0,
        )
        assert ev.warnings == []

    def test_key_takeaways_default_empty_list(self):
        ev = AIEvaluation(
            ai_confidence=0.5,
            risk_level="medium",
            market_regime="quiet",
            reasoning="test",
            model_used="m",
            evaluation_latency_ms=0,
        )
        assert ev.key_takeaways == []

    def test_data_completeness_score_none_by_default(self):
        ev = AIEvaluation(
            ai_confidence=0.5,
            risk_level="medium",
            market_regime="quiet",
            reasoning="test",
            model_used="m",
            evaluation_latency_ms=0,
        )
        assert ev.data_completeness_score is None

    def test_confidence_drivers_default_empty_list(self):
        ev = AIEvaluation(
            ai_confidence=0.5,
            risk_level="medium",
            market_regime="quiet",
            reasoning="test",
            model_used="m",
            evaluation_latency_ms=0,
        )
        assert ev.confidence_drivers == []

    def test_risk_drivers_default_empty_list(self):
        ev = AIEvaluation(
            ai_confidence=0.5,
            risk_level="medium",
            market_regime="quiet",
            reasoning="test",
            model_used="m",
            evaluation_latency_ms=0,
        )
        assert ev.risk_drivers == []

    def test_risk_level_extreme_is_accepted(self):
        ev = AIEvaluation(
            ai_confidence=0.5,
            risk_level="extreme",
            market_regime="volatile",
            reasoning="extremely risky conditions",
            model_used="m",
            evaluation_latency_ms=0,
        )
        assert ev.risk_level == "extreme"

    def test_new_fields_with_explicit_values(self):
        ev = AIEvaluation(
            ai_confidence=0.75,
            risk_level="high",
            market_regime="volatile",
            reasoning="test with all fields",
            model_used="deepseek-reasoner",
            evaluation_latency_ms=100,
            recommended_action="reduce_exposure",
            suggested_position_size_pct=5.0,
            suggested_leverage=1.0,
            warnings=["high volatility", "low liquidity"],
            key_takeaways=["RSI overbought", "MACD bearish divergence"],
            data_completeness_score=0.85,
            confidence_drivers=["strong trend"],
            risk_drivers=["low volume"],
        )
        assert ev.recommended_action == "reduce_exposure"
        assert ev.suggested_position_size_pct == pytest.approx(5.0)
        assert ev.suggested_leverage == pytest.approx(1.0)
        assert len(ev.warnings) == 2
        assert len(ev.key_takeaways) == 2
        assert ev.data_completeness_score == pytest.approx(0.85)
        assert ev.confidence_drivers == ["strong trend"]
        assert ev.risk_drivers == ["low volume"]

    def test_position_size_pct_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            AIEvaluation(
                ai_confidence=0.5,
                risk_level="medium",
                market_regime="quiet",
                reasoning="test",
                model_used="m",
                evaluation_latency_ms=0,
                suggested_position_size_pct=150.0,
            )

    def test_data_completeness_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            AIEvaluation(
                ai_confidence=0.5,
                risk_level="medium",
                market_regime="quiet",
                reasoning="test",
                model_used="m",
                evaluation_latency_ms=0,
                data_completeness_score=1.5,
            )

    def test_backward_compat_existing_fields_unchanged(self):
        """Existing construction patterns must still work."""
        ev = AIEvaluation(
            ai_confidence=0.82,
            risk_level="low",
            market_regime="trending",
            reasoning="RSI indicates bullish momentum.",
            model_used="deepseek-reasoner",
            evaluation_latency_ms=120,
        )
        assert ev.ai_confidence == pytest.approx(0.82)
        assert ev.risk_level == "low"
        assert ev.signal_quality == "usable"
        assert ev.recommended_handling == "store_only"
        # New fields default safely
        assert ev.recommended_action is None
        assert ev.suggested_leverage is None
        assert ev.warnings == []


# ======================================================================
# 3c: JSON decoding hardening
# ======================================================================

class TestJsonDecodingHardening:
    """Test safe extraction helpers and _build_evaluation with new fields."""

    def test_extract_optional_str_present(self):
        assert _extract_optional_str({"recommended_action": "hold"}, "recommended_action") == "hold"

    def test_extract_optional_str_missing(self):
        assert _extract_optional_str({}, "recommended_action") is None

    def test_extract_optional_str_null(self):
        assert _extract_optional_str({"recommended_action": None}, "recommended_action") is None

    def test_extract_optional_float_present(self):
        assert _extract_optional_float({"suggested_leverage": 2.0}, "suggested_leverage") == pytest.approx(2.0)

    def test_extract_optional_float_missing(self):
        assert _extract_optional_float({}, "suggested_leverage") is None

    def test_extract_optional_float_null(self):
        assert _extract_optional_float({"suggested_leverage": None}, "suggested_leverage") is None

    def test_extract_optional_float_malformed(self):
        result = _extract_optional_float({"suggested_leverage": "not_a_number"}, "suggested_leverage")
        assert result is None

    def test_extract_optional_list_present(self):
        result = _extract_optional_list({"warnings": ["high vol"]}, "warnings")
        assert result == ["high vol"]

    def test_extract_optional_list_missing(self):
        assert _extract_optional_list({}, "warnings") == []

    def test_extract_optional_list_null(self):
        assert _extract_optional_list({"warnings": None}, "warnings") == []

    def test_extract_optional_list_non_list(self):
        result = _extract_optional_list({"warnings": "string_not_list"}, "warnings")
        assert result == []

    def test_build_evaluation_with_all_new_fields(self):
        evaluator = LLMEvaluator(api_key="sk-test", threshold=0.5)
        parsed = {
            "ai_confidence": 0.78,
            "risk_level": "high",
            "market_regime": "volatile",
            "reasoning": "High volatility detected.",
            "ai_risk_score": 0.8,
            "signal_quality": "weak",
            "recommended_handling": "review_required",
            "contradictions": ["RSI bullish, MACD bearish"],
            "missing_context": ["order flow"],
            "summary": "Volatility spike",
            "recommended_action": "reduce_exposure",
            "suggested_position_size_pct": 3.0,
            "suggested_leverage": 1.0,
            "warnings": ["high volatility", "thin order book"],
            "key_takeaways": ["Avoid new positions"],
            "data_completeness_score": 0.7,
            "confidence_drivers": ["momentum"],
            "risk_drivers": ["volatility", "liquidity"],
        }
        ev = evaluator._build_evaluation(parsed, "test-model", 50)
        assert ev.recommended_action == "reduce_exposure"
        assert ev.suggested_position_size_pct == pytest.approx(3.0)
        assert ev.suggested_leverage == pytest.approx(1.0)
        assert ev.warnings == ["high volatility", "thin order book"]
        assert ev.key_takeaways == ["Avoid new positions"]
        assert ev.data_completeness_score == pytest.approx(0.7)
        assert ev.confidence_drivers == ["momentum"]
        assert ev.risk_drivers == ["volatility", "liquidity"]

    def test_build_evaluation_missing_new_fields_uses_defaults(self):
        """Missing new optional fields degrade safely to defaults."""
        evaluator = LLMEvaluator(api_key="sk-test", threshold=0.5)
        parsed = {
            "ai_confidence": 0.5,
            "risk_level": "medium",
            "market_regime": "quiet",
            "reasoning": "No new fields.",
        }
        ev = evaluator._build_evaluation(parsed, "test-model", 10)
        assert ev.recommended_action is None
        assert ev.suggested_position_size_pct is None
        assert ev.suggested_leverage is None
        assert ev.warnings == []
        assert ev.key_takeaways == []
        assert ev.data_completeness_score is None
        assert ev.confidence_drivers == []
        assert ev.risk_drivers == []

    def test_build_evaluation_malformed_new_fields_uses_defaults(self):
        """Malformed new fields degrade gracefully."""
        evaluator = LLMEvaluator(api_key="sk-test", threshold=0.5)
        parsed = {
            "ai_confidence": 0.5,
            "risk_level": "medium",
            "market_regime": "quiet",
            "reasoning": "Malformed new fields.",
            "recommended_action": 123,  # wrong type
            "suggested_leverage": "not_a_number",  # wrong type
            "warnings": "not_a_list",  # wrong type
            "data_completeness_score": "bad",  # wrong type
        }
        ev = evaluator._build_evaluation(parsed, "test-model", 10)
        # recommended_action gets stringified to "123" — this is acceptable
        assert ev.recommended_action is not None  # str(123) == "123"
        assert ev.suggested_leverage is None  # malformed float
        assert ev.warnings == []  # malformed list
        assert ev.data_completeness_score is None  # malformed float

    def test_safe_default_evaluation_includes_new_fields(self):
        """Safe default evaluation should have all new fields at defaults."""
        ev = _safe_default_evaluation("m", 0)
        assert ev.recommended_action is None
        assert ev.suggested_position_size_pct is None
        assert ev.suggested_leverage is None
        assert ev.warnings == []
        assert ev.key_takeaways == []
        assert ev.data_completeness_score is None
        assert ev.confidence_drivers == []
        assert ev.risk_drivers == []


# ======================================================================
# Safety invariants
# ======================================================================

class TestSafetyInvariants:
    """Ensure LLM output cannot set execution authority or modulate strategy."""

    def test_no_llm_output_can_set_can_execute(self):
        """The AIEvaluation model has no can_execute field at all."""
        field_names = set(AIEvaluation.model_fields.keys())
        assert "can_execute" not in field_names
        assert "execution_authority" not in field_names

    def test_safe_default_does_not_set_execution(self):
        ev = _safe_default_evaluation("m", 0)
        assert ev.recommended_handling == "store_only"
        assert ev.signal_quality == "weak"
        assert ev.ai_confidence == 0.0

    def test_no_strategy_modulation_fields(self):
        """AIEvaluation must not contain fields that directly modulate strategy."""
        field_names = set(AIEvaluation.model_fields.keys())
        forbidden = {"strategy_weight", "strategy_multiplier", "confidence_modulation"}
        for f in forbidden:
            assert f not in field_names, f"Forbidden field {f} found in AIEvaluation"


# ======================================================================
# 3d: CryptoSignal optional fields
# ======================================================================

class TestCryptoSignalOptionalFields:
    """Test the new optional fields on CryptoSignal."""

    def test_existing_construction_still_works(self):
        """Old code creating CryptoSignal without new fields must work."""
        sig = CryptoSignal(
            source="test",
            asset="BTC",
            signal_type=SignalType.TECHNICAL,
            direction=Direction.BULLISH,
            strength=0.75,
            confidence=0.8,
            rainbow_score=0.85,
        )
        assert sig.timeframe is None
        assert sig.stop_loss is None
        assert sig.take_profit is None
        assert sig.leverage is None

    def test_new_optional_fields_explicit(self):
        sig = CryptoSignal(
            source="test",
            asset="ETH",
            signal_type=SignalType.TECHNICAL,
            direction=Direction.BEARISH,
            strength=0.6,
            confidence=0.7,
            rainbow_score=0.65,
            timeframe="1h",
            stop_loss=1850.0,
            take_profit=1750.0,
            leverage=2.0,
        )
        assert sig.timeframe == "1h"
        assert sig.stop_loss == pytest.approx(1850.0)
        assert sig.take_profit == pytest.approx(1750.0)
        assert sig.leverage == pytest.approx(2.0)


# ======================================================================
# End-to-end: evaluator integration with new prompt/response
# ======================================================================

class TestEvaluatorWithNewFields:
    """End-to-end: evaluator correctly processes responses with new fields."""

    @pytest.mark.anyio
    async def test_full_response_with_new_fields(self, evaluator: LLMEvaluator) -> None:
        payload = {
            "ai_confidence": 0.6,
            "risk_level": "high",
            "market_regime": "volatile",
            "reasoning": "High volatility; reduce exposure.",
            "ai_risk_score": 0.8,
            "signal_quality": "weak",
            "recommended_handling": "review_required",
            "contradictions": [],
            "missing_context": ["order_flow"],
            "summary": "Volatility spike; caution advised.",
            "recommended_action": "reduce_exposure",
            "suggested_position_size_pct": 3.0,
            "suggested_leverage": None,
            "warnings": ["high volatility"],
            "key_takeaways": ["Avoid new positions"],
            "data_completeness_score": 0.6,
            "confidence_drivers": ["momentum"],
            "risk_drivers": ["volatility"],
        }
        with patch.object(
            evaluator._client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=_mock_response(payload),
        ):
            result = await evaluator.evaluate(_make_signal(0.8))

        assert result is not None
        assert result.recommended_action == "reduce_exposure"
        assert result.suggested_position_size_pct == pytest.approx(3.0)
        assert result.suggested_leverage is None
        assert "high volatility" in result.warnings
        assert "Avoid new positions" in result.key_takeaways
        assert result.data_completeness_score == pytest.approx(0.6)
        assert result.confidence_drivers == ["momentum"]
        assert result.risk_drivers == ["volatility"]

    @pytest.mark.anyio
    async def test_old_format_response_with_new_fields_defaulting(self, evaluator: LLMEvaluator) -> None:
        """Old-format response (missing new fields) → new fields get safe defaults."""
        payload = {
            "ai_confidence": 0.5,
            "risk_level": "medium",
            "market_regime": "ranging",
            "reasoning": "Neutral outlook.",
        }
        with patch.object(
            evaluator._client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=_mock_response(payload),
        ):
            result = await evaluator.evaluate(_make_signal(0.8))

        assert result is not None
        assert result.recommended_action is None
        assert result.suggested_position_size_pct is None
        assert result.suggested_leverage is None
        assert result.warnings == []
        assert result.key_takeaways == []
        assert result.data_completeness_score is None
        assert result.confidence_drivers == []
        assert result.risk_drivers == []

    @pytest.mark.anyio
    async def test_invalid_json_triggers_safe_fallback_with_new_fields(self, evaluator: LLMEvaluator) -> None:
        """Invalid JSON returns safe default with all new fields at defaults."""
        bad = MagicMock()
        bad.choices = [MagicMock()]
        bad.choices[0].message.content = "not valid json"
        with patch.object(
            evaluator._client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=bad,
        ):
            result = await evaluator.evaluate(_make_signal(0.9))
        assert result is not None
        assert result.recommended_action is None
        assert result.suggested_leverage is None
        assert result.warnings == []
        assert result.key_takeaways == []

    @pytest.mark.anyio
    async def test_risk_level_extreme_in_response(self, evaluator: LLMEvaluator) -> None:
        """The evaluator should accept risk_level='extreme' from LLM JSON."""
        payload = {
            "ai_confidence": 0.3,
            "risk_level": "extreme",
            "market_regime": "volatile",
            "reasoning": "Extreme risk conditions.",
            "recommended_action": "hold",
            "warnings": ["dangerous market"],
        }
        with patch.object(
            evaluator._client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=_mock_response(payload),
        ):
            result = await evaluator.evaluate(_make_signal(0.8))

        assert result is not None
        assert result.risk_level == "extreme"
        assert result.recommended_action == "hold"
