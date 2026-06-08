"""Tests for Issue #24 — Rule-Based Review Policy."""

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
from core.signals.review_policy import ReviewPolicy
from rainbow.evaluation.models import AIEvaluation


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
        invalidation={},
        raw_refs=[],
    )
    defaults.update(overrides)
    return CanonicalSignalEnvelope(**defaults)


def _make_evaluation(**overrides) -> AIEvaluation:
    defaults = dict(
        ai_confidence=0.5,
        risk_level="medium",
        market_regime="quiet",
        reasoning="test",
        model_used="test",
        evaluation_latency_ms=0,
    )
    defaults.update(overrides)
    return AIEvaluation(**defaults)


@pytest.fixture
def policy() -> ReviewPolicy:
    return ReviewPolicy()


# ======================================================================
# Rule 1: data_quality.status != "ok" → "review_required"
# ======================================================================

class TestRule1DataQuality:
    def test_degraded_data(self, policy: ReviewPolicy):
        env = _make_envelope(
            data_quality=DataQuality(status=DataQualityStatus.DEGRADED),
        )
        ev = _make_evaluation(ai_confidence=0.95, recommended_handling="summary")
        assert policy.decide(ev, env) == "review_required"

    def test_stale_data(self, policy: ReviewPolicy):
        env = _make_envelope(
            data_quality=DataQuality(status=DataQualityStatus.STALE),
        )
        ev = _make_evaluation(ai_confidence=0.95, recommended_handling="summary")
        assert policy.decide(ev, env) == "review_required"

    def test_unavailable_data(self, policy: ReviewPolicy):
        env = _make_envelope(
            data_quality=DataQuality(status=DataQualityStatus.UNAVAILABLE),
        )
        ev = _make_evaluation(ai_confidence=0.95, recommended_handling="summary")
        assert policy.decide(ev, env) == "review_required"

    def test_ok_data_not_triggered(self, policy: ReviewPolicy):
        env = _make_envelope(
            data_quality=DataQuality(status=DataQualityStatus.OK),
        )
        ev = _make_evaluation(ai_confidence=0.5, recommended_handling="store_only")
        assert policy.decide(ev, env) == "store_only"


# ======================================================================
# Rule 2: risk_score >= 0.75 → "risk_summary"
# ======================================================================

class TestRule2HighRisk:
    def test_exactly_075(self, policy: ReviewPolicy):
        env = _make_envelope(risk_score=0.75)
        ev = _make_evaluation(ai_confidence=0.5, recommended_handling="store_only")
        assert policy.decide(ev, env) == "risk_summary"

    def test_above_075(self, policy: ReviewPolicy):
        env = _make_envelope(risk_score=0.9)
        ev = _make_evaluation(ai_confidence=0.5, recommended_handling="store_only")
        assert policy.decide(ev, env) == "risk_summary"

    def test_below_075_not_triggered(self, policy: ReviewPolicy):
        env = _make_envelope(risk_score=0.74)
        ev = _make_evaluation(ai_confidence=0.5, recommended_handling="store_only")
        assert policy.decide(ev, env) == "store_only"


# ======================================================================
# Rule 3: signal_quality == "contradictory" → "review_required"
# ======================================================================

class TestRule3Contradictory:
    def test_contradictory_signal(self, policy: ReviewPolicy):
        env = _make_envelope(risk_score=0.3)
        ev = _make_evaluation(
            ai_confidence=0.8,
            signal_quality="contradictory",
            recommended_handling="summary",
        )
        assert policy.decide(ev, env) == "review_required"

    def test_non_contradictory_not_triggered(self, policy: ReviewPolicy):
        env = _make_envelope(risk_score=0.3)
        for quality in ["strong", "usable", "weak"]:
            ev = _make_evaluation(
                signal_quality=quality,
                recommended_handling="store_only",
            )
            assert policy.decide(ev, env) == "store_only"


# ======================================================================
# Rule 4: recommended_handling == "suppress" → "suppress"
# ======================================================================

class TestRule4Suppress:
    def test_suppress_handled(self, policy: ReviewPolicy):
        env = _make_envelope(risk_score=0.3)
        ev = _make_evaluation(
            ai_confidence=0.5,
            recommended_handling="suppress",
        )
        assert policy.decide(ev, env) == "suppress"

    def test_non_suppress_not_triggered(self, policy: ReviewPolicy):
        env = _make_envelope(risk_score=0.3)
        for handling in ["store_only", "summary", "risk_summary", "review_required"]:
            ev = _make_evaluation(recommended_handling=handling)
            result = policy.decide(ev, env)
            # Should not be "suppress" for these (might be store_only or something else)
            assert result != "suppress" or handling == "suppress"


# ======================================================================
# Rule 5: ai_confidence >= 0.7 AND recommended_handling in {summary, risk_summary}
# ======================================================================

class TestRule5HighConfidence:
    def test_confident_summary(self, policy: ReviewPolicy):
        env = _make_envelope(risk_score=0.3)
        ev = _make_evaluation(
            ai_confidence=0.7,
            recommended_handling="summary",
        )
        assert policy.decide(ev, env) == "summary"

    def test_confident_risk_summary(self, policy: ReviewPolicy):
        env = _make_envelope(risk_score=0.3)
        ev = _make_evaluation(
            ai_confidence=0.7,
            recommended_handling="risk_summary",
        )
        assert policy.decide(ev, env) == "risk_summary"

    def test_low_confidence_ignores_summary(self, policy: ReviewPolicy):
        env = _make_envelope(risk_score=0.3)
        ev = _make_evaluation(
            ai_confidence=0.69,
            recommended_handling="summary",
        )
        assert policy.decide(ev, env) == "store_only"

    def test_confident_but_store_only(self, policy: ReviewPolicy):
        env = _make_envelope(risk_score=0.3)
        ev = _make_evaluation(
            ai_confidence=0.9,
            recommended_handling="store_only",
        )
        assert policy.decide(ev, env) == "store_only"

    def test_confident_but_review_required(self, policy: ReviewPolicy):
        env = _make_envelope(risk_score=0.3)
        ev = _make_evaluation(
            ai_confidence=0.9,
            recommended_handling="review_required",
        )
        assert policy.decide(ev, env) == "store_only"


# ======================================================================
# Rule 6: default → "store_only"
# ======================================================================

class TestRule6Default:
    def test_no_rules_matched(self, policy: ReviewPolicy):
        env = _make_envelope(risk_score=0.3)
        ev = _make_evaluation(
            ai_confidence=0.5,
            recommended_handling="store_only",
        )
        assert policy.decide(ev, env) == "store_only"

    def test_low_confidence_with_summary_falls_through(self, policy: ReviewPolicy):
        env = _make_envelope(risk_score=0.3)
        ev = _make_evaluation(
            ai_confidence=0.4,
            recommended_handling="summary",
        )
        assert policy.decide(ev, env) == "store_only"


# ======================================================================
# Precedence: deterministic gates override LLM recommendations
# ======================================================================

class TestDeterministicPrecedence:
    def test_data_quality_overrides_llm_summary(self, policy: ReviewPolicy):
        """Bad data → review_required even if LLM says summary with high confidence."""
        env = _make_envelope(
            risk_score=0.1,
            data_quality=DataQuality(status=DataQualityStatus.DEGRADED),
        )
        ev = _make_evaluation(
            ai_confidence=0.95,
            recommended_handling="summary",
            signal_quality="strong",
        )
        assert policy.decide(ev, env) == "review_required"

    def test_high_risk_overrides_llm_store_only(self, policy: ReviewPolicy):
        """High risk → risk_summary even if LLM says store_only."""
        env = _make_envelope(risk_score=0.8)
        ev = _make_evaluation(
            ai_confidence=0.1,
            recommended_handling="store_only",
            signal_quality="strong",
        )
        assert policy.decide(ev, env) == "risk_summary"

    def test_data_quality_beats_high_risk(self, policy: ReviewPolicy):
        """Rule 1 (data quality) has highest priority."""
        env = _make_envelope(
            risk_score=0.9,
            data_quality=DataQuality(status=DataQualityStatus.STALE),
        )
        ev = _make_evaluation(ai_confidence=0.5, recommended_handling="store_only")
        assert policy.decide(ev, env) == "review_required"

    def test_risk_beats_contradictory(self, policy: ReviewPolicy):
        """Rule 2 (risk) beats rule 3 (contradictory)."""
        env = _make_envelope(risk_score=0.8)
        ev = _make_evaluation(
            ai_confidence=0.5,
            signal_quality="contradictory",
            recommended_handling="review_required",
        )
        assert policy.decide(ev, env) == "risk_summary"

    def test_contradictory_beats_suppress(self, policy: ReviewPolicy):
        """Rule 3 (contradictory) beats rule 4 (suppress)."""
        env = _make_envelope(risk_score=0.3)
        ev = _make_evaluation(
            ai_confidence=0.5,
            signal_quality="contradictory",
            recommended_handling="suppress",
        )
        assert policy.decide(ev, env) == "review_required"

    def test_suppress_beats_high_confidence(self, policy: ReviewPolicy):
        """Rule 4 (suppress) beats rule 5 (LLM recommendation)."""
        env = _make_envelope(risk_score=0.3)
        ev = _make_evaluation(
            ai_confidence=0.9,
            recommended_handling="suppress",
        )
        assert policy.decide(ev, env) == "suppress"
