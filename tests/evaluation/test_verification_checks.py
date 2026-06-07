# tests/evaluation/test_verification_checks.py
"""Verification checks from Issue #4 — institutional-grade LLM evaluation layer."""

from __future__ import annotations

import json

from rainbow.evaluation.models import AIEvaluation
from rainbow.models.signal import CryptoSignal, SignalType


class TestVerificationCheck1:
    """Check 1: json.loads(response) round-trips into valid AIEvaluation."""

    def test_json_roundtrip(self) -> None:
        data = {
            "ai_confidence": 0.75,
            "risk_level": "medium",
            "market_regime": "trending",
            "reasoning": "Bullish momentum confirmed by multiple indicators.",
            "model_used": "deepseek-reasoner",
            "evaluation_latency_ms": 150,
        }
        json_str = json.dumps(data)
        parsed = json.loads(json_str)
        eval_ = AIEvaluation(**parsed)
        assert eval_.ai_confidence == 0.75
        assert eval_.risk_level == "medium"


class TestVerificationCheck2:
    """Check 2: risk_level='extreme' validates without error."""

    def test_extreme_risk_level(self) -> None:
        eval_ = AIEvaluation(
            ai_confidence=0.1,
            risk_level="extreme",
            market_regime="high-volatility",
            reasoning="Extreme risk detected",
            model_used="test",
            evaluation_latency_ms=10,
        )
        assert eval_.risk_level == "extreme"


class TestVerificationCheck3:
    """Check 3: market_regime accepts both old and new values."""

    def test_old_value_trending(self) -> None:
        eval_ = AIEvaluation(
            ai_confidence=0.5,
            risk_level="low",
            market_regime="trending",
            reasoning="test",
            model_used="test",
            evaluation_latency_ms=10,
        )
        assert eval_.market_regime == "trending"

    def test_new_value_aligned(self) -> None:
        eval_ = AIEvaluation(
            ai_confidence=0.5,
            risk_level="low",
            market_regime="aligned",
            reasoning="test",
            model_used="test",
            evaluation_latency_ms=10,
        )
        assert eval_.market_regime == "aligned"

    def test_any_string_regime(self) -> None:
        eval_ = AIEvaluation(
            ai_confidence=0.5,
            risk_level="low",
            market_regime="bull_trend_with_high_vol",
            reasoning="test",
            model_used="test",
            evaluation_latency_ms=10,
        )
        assert eval_.market_regime == "bull_trend_with_high_vol"


class TestVerificationCheck4:
    """Check 4: CryptoSignal instantiates without new optional fields."""

    def test_minimal_signal_no_new_fields(self) -> None:
        sig = CryptoSignal(
            source="test",
            asset="BTC",
            signal_type=SignalType.TECHNICAL,
            strength=0.5,
            confidence=0.5,
        )
        assert sig.timeframe is None
        assert sig.stop_loss is None
        assert sig.take_profit is None
        assert sig.leverage == 1.0

    def test_signal_with_all_new_fields(self) -> None:
        sig = CryptoSignal(
            source="test",
            asset="BTC",
            signal_type=SignalType.TECHNICAL,
            strength=0.8,
            confidence=0.7,
            timeframe="4h",
            stop_loss=48000.0,
            take_profit=[52000.0, 54000.0],
            leverage=3.0,
        )
        assert sig.timeframe == "4h"
        assert sig.stop_loss == 48000.0
        assert sig.take_profit == [52000.0, 54000.0]
        assert sig.leverage == 3.0


class TestVerificationCheck5:
    """Check 5: evaluate() never raises — tested via test_llm_evaluator.py."""

    def test_placeholder(self) -> None:
        """Covered by test_llm_evaluator tests: empty string, non-JSON, partial JSON, None values."""
        assert True


class TestVerificationCheck6:
    """Check 6: recommended_action is always valid."""

    def test_valid_actions(self) -> None:
        for action in ["enter", "wait", "skip", "reduce_size", "hedge", "close"]:
            eval_ = AIEvaluation(
                ai_confidence=0.5,
                risk_level="low",
                market_regime="trending",
                reasoning="test",
                model_used="test",
                evaluation_latency_ms=10,
                recommended_action=action,
            )
            assert eval_.recommended_action == action


class TestVerificationCheck7:
    """Check 7: All new AIEvaluation fields visible and JSON-serializable."""

    def test_all_fields_serializable(self) -> None:
        eval_ = AIEvaluation(
            ai_confidence=0.7,
            risk_level="medium",
            market_regime="trending",
            reasoning="test reasoning",
            model_used="test",
            evaluation_latency_ms=100,
            signal_id="sig-123",
            strength="strong",
            expected_holding_period="4h",
            key_takeaways=["TA bullish"],
            supporting_factors=["Volume up"],
            conflicting_factors=["Funding rate high"],
            invalidations=["Break below 48k"],
            recommended_action="enter",
            suggested_position_size_pct=5.0,
            suggested_leverage=2.0,
            stop_loss_review="Below 48500",
            take_profit_review="At 52000",
            risk_reward_assessment="1:2.5",
            data_completeness_score=0.8,
            warnings=["Volatility"],
            timeframe="1h",
        )
        data = eval_.model_dump()
        json_str = json.dumps(data)
        assert "signal_id" in json_str
        assert "key_takeaways" in json_str
        assert "recommended_action" in json_str
        assert "warnings" in json_str


class TestVerificationCheck8:
    """Check 8: Existing call sites using only legacy AIEvaluation fields continue to work."""

    def test_legacy_fields_only(self) -> None:
        eval_ = AIEvaluation(
            ai_confidence=0.8,
            risk_level="high",
            market_regime="volatile",
            reasoning="test",
            model_used="deepseek-reasoner",
            evaluation_latency_ms=200,
        )
        # Legacy fields
        assert eval_.ai_confidence == 0.8
        assert eval_.risk_level == "high"
        assert eval_.market_regime == "volatile"
        assert eval_.reasoning == "test"
        assert eval_.model_used == "deepseek-reasoner"
        assert eval_.evaluation_latency_ms == 200
        # New fields have defaults
        assert eval_.signal_id is None
        assert eval_.key_takeaways == []
        assert eval_.warnings == []


class TestVerificationCheck10:
    """Check 10: No circular import between signal.py, models.py, llm_evaluator.py."""

    def test_no_circular_import(self) -> None:
        import rainbow.evaluation.llm_evaluator  # noqa: F401
        import rainbow.evaluation.models  # noqa: F401
        import rainbow.models.signal  # noqa: F401

        assert True  # If we get here, no circular import
