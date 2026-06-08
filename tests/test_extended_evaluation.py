"""Tests for Issue #22 — Extended AIEvaluation schema."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from rainbow.evaluation.models import AIEvaluation


class TestExistingFields:
    """Existing fields must still work as before."""

    def test_create_minimal_evaluation(self):
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
        assert ev.market_regime == "trending"
        assert ev.model_used == "deepseek-reasoner"
        assert ev.evaluation_latency_ms == 120

    def test_confidence_bounds_low(self):
        with pytest.raises(ValidationError):
            AIEvaluation(
                ai_confidence=-0.1,
                risk_level="low",
                market_regime="quiet",
                reasoning="test",
                model_used="m",
                evaluation_latency_ms=0,
            )

    def test_confidence_bounds_high(self):
        with pytest.raises(ValidationError):
            AIEvaluation(
                ai_confidence=1.5,
                risk_level="low",
                market_regime="quiet",
                reasoning="test",
                model_used="m",
                evaluation_latency_ms=0,
            )

    def test_invalid_risk_level(self):
        with pytest.raises(ValidationError):
            AIEvaluation(
                ai_confidence=0.5,
                risk_level="extreme",
                market_regime="quiet",
                reasoning="test",
                model_used="m",
                evaluation_latency_ms=0,
            )

    def test_invalid_market_regime(self):
        with pytest.raises(ValidationError):
            AIEvaluation(
                ai_confidence=0.5,
                risk_level="low",
                market_regime="crash",
                reasoning="test",
                model_used="m",
                evaluation_latency_ms=0,
            )


class TestNewFieldsDefaults:
    """New fields must have safe defaults for backward compatibility."""

    def test_default_ai_risk_score(self):
        ev = AIEvaluation(
            ai_confidence=0.5,
            risk_level="medium",
            market_regime="quiet",
            reasoning="test",
            model_used="m",
            evaluation_latency_ms=0,
        )
        assert ev.ai_risk_score == pytest.approx(0.5)

    def test_default_signal_quality(self):
        ev = AIEvaluation(
            ai_confidence=0.5,
            risk_level="medium",
            market_regime="quiet",
            reasoning="test",
            model_used="m",
            evaluation_latency_ms=0,
        )
        assert ev.signal_quality == "usable"

    def test_default_recommended_handling(self):
        ev = AIEvaluation(
            ai_confidence=0.5,
            risk_level="medium",
            market_regime="quiet",
            reasoning="test",
            model_used="m",
            evaluation_latency_ms=0,
        )
        assert ev.recommended_handling == "store_only"

    def test_default_contradictions(self):
        ev = AIEvaluation(
            ai_confidence=0.5,
            risk_level="medium",
            market_regime="quiet",
            reasoning="test",
            model_used="m",
            evaluation_latency_ms=0,
        )
        assert ev.contradictions == []

    def test_default_missing_context(self):
        ev = AIEvaluation(
            ai_confidence=0.5,
            risk_level="medium",
            market_regime="quiet",
            reasoning="test",
            model_used="m",
            evaluation_latency_ms=0,
        )
        assert ev.missing_context == []

    def test_default_summary(self):
        ev = AIEvaluation(
            ai_confidence=0.5,
            risk_level="medium",
            market_regime="quiet",
            reasoning="test",
            model_used="m",
            evaluation_latency_ms=0,
        )
        assert ev.summary == ""


class TestNewFieldsExplicitValues:
    """New fields accept valid explicit values."""

    def test_ai_risk_score_explicit(self):
        ev = AIEvaluation(
            ai_confidence=0.5,
            risk_level="high",
            market_regime="volatile",
            reasoning="test",
            model_used="m",
            evaluation_latency_ms=0,
            ai_risk_score=0.9,
        )
        assert ev.ai_risk_score == pytest.approx(0.9)

    def test_signal_quality_strong(self):
        ev = AIEvaluation(
            ai_confidence=0.5,
            risk_level="low",
            market_regime="trending",
            reasoning="test",
            model_used="m",
            evaluation_latency_ms=0,
            signal_quality="strong",
        )
        assert ev.signal_quality == "strong"

    def test_signal_quality_weak(self):
        ev = AIEvaluation(
            ai_confidence=0.5,
            risk_level="medium",
            market_regime="quiet",
            reasoning="test",
            model_used="m",
            evaluation_latency_ms=0,
            signal_quality="weak",
        )
        assert ev.signal_quality == "weak"

    def test_signal_quality_contradictory(self):
        ev = AIEvaluation(
            ai_confidence=0.5,
            risk_level="high",
            market_regime="volatile",
            reasoning="test",
            model_used="m",
            evaluation_latency_ms=0,
            signal_quality="contradictory",
        )
        assert ev.signal_quality == "contradictory"

    def test_all_handling_values(self):
        for handling in ["store_only", "summary", "risk_summary", "review_required", "suppress"]:
            ev = AIEvaluation(
                ai_confidence=0.5,
                risk_level="medium",
                market_regime="quiet",
                reasoning="test",
                model_used="m",
                evaluation_latency_ms=0,
                recommended_handling=handling,
            )
            assert ev.recommended_handling == handling

    def test_contradictions_list(self):
        ev = AIEvaluation(
            ai_confidence=0.5,
            risk_level="medium",
            market_regime="quiet",
            reasoning="test",
            model_used="m",
            evaluation_latency_ms=0,
            contradictions=["RSI bullish vs MACD bearish", "Volume declining"],
        )
        assert len(ev.contradictions) == 2

    def test_missing_context_list(self):
        ev = AIEvaluation(
            ai_confidence=0.5,
            risk_level="medium",
            market_regime="quiet",
            reasoning="test",
            model_used="m",
            evaluation_latency_ms=0,
            missing_context=["order_flow", "funding_rate"],
        )
        assert len(ev.missing_context) == 2

    def test_summary_string(self):
        ev = AIEvaluation(
            ai_confidence=0.5,
            risk_level="medium",
            market_regime="quiet",
            reasoning="test",
            model_used="m",
            evaluation_latency_ms=0,
            summary="Bullish entry signal with moderate risk.",
        )
        assert "Bullish" in ev.summary


class TestValidation:
    """Invalid values for new fields are rejected."""

    def test_invalid_signal_quality(self):
        with pytest.raises(ValidationError):
            AIEvaluation(
                ai_confidence=0.5,
                risk_level="low",
                market_regime="quiet",
                reasoning="test",
                model_used="m",
                evaluation_latency_ms=0,
                signal_quality="amazing",
            )

    def test_invalid_recommended_handling(self):
        with pytest.raises(ValidationError):
            AIEvaluation(
                ai_confidence=0.5,
                risk_level="low",
                market_regime="quiet",
                reasoning="test",
                model_used="m",
                evaluation_latency_ms=0,
                recommended_handling="auto_trade",
            )

    def test_ai_risk_score_out_of_range(self):
        with pytest.raises(ValidationError):
            AIEvaluation(
                ai_confidence=0.5,
                risk_level="low",
                market_regime="quiet",
                reasoning="test",
                model_used="m",
                evaluation_latency_ms=0,
                ai_risk_score=2.0,
            )

    def test_ai_risk_score_negative(self):
        with pytest.raises(ValidationError):
            AIEvaluation(
                ai_confidence=0.5,
                risk_level="low",
                market_regime="quiet",
                reasoning="test",
                model_used="m",
                evaluation_latency_ms=0,
                ai_risk_score=-0.1,
            )


class TestBackwardCompatibility:
    """Existing code creating evaluations must still work."""

    def test_old_style_construction_with_model(self):
        """The existing test_llm_evaluator pattern must still work."""
        parsed = {
            "ai_confidence": 0.82,
            "risk_level": "low",
            "market_regime": "trending",
            "reasoning": "RSI indicates bullish momentum.",
        }
        ev = AIEvaluation(
            ai_confidence=float(parsed["ai_confidence"]),
            risk_level=parsed["risk_level"],
            market_regime=parsed["market_regime"],
            reasoning=str(parsed["reasoning"])[:300],
            model_used="deepseek-reasoner",
            evaluation_latency_ms=42,
        )
        assert ev.ai_confidence == pytest.approx(0.82)
        # New fields get defaults
        assert ev.signal_quality == "usable"
        assert ev.recommended_handling == "store_only"
        assert ev.ai_risk_score == pytest.approx(0.5)
        assert ev.summary == ""
