"""Tests for Issue #26 — LLM-Powered Compact Summaries."""

from __future__ import annotations

from core.signals.envelope import (
    Actionability,
    CanonicalSignalEnvelope,
    DataQuality,
    DataQualityStatus,
    SignalClass,
    SignalDirection,
    SignalPriority,
)
from core.signals.summarizer import format_signal_summary
from rainbow.evaluation.models import AIEvaluation


def _make_envelope(**overrides) -> CanonicalSignalEnvelope:
    defaults = dict(
        signal_class=SignalClass.ENTRY,
        subtype="test",
        source="unit-test",
        asset="BTC/USDT",
        direction=SignalDirection.BULLISH,
        confidence=0.72,
        risk_score=0.35,
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
        ai_confidence=0.72,
        risk_level="low",
        market_regime="trending",
        reasoning="RSI oversold + volume spike",
        model_used="test-model",
        evaluation_latency_ms=50,
    )
    defaults.update(overrides)
    return AIEvaluation(**defaults)


class TestBasicFormatting:
    def test_with_evaluation(self):
        env = _make_envelope()
        ev = _make_evaluation()
        result = format_signal_summary(env, ev)
        assert "[BTC/USDT]" in result
        assert "ENTRY" in result
        assert "bullish" in result
        assert "conf:" in result
        assert "0.72" in result
        assert "risk:" in result
        assert "0.35" in result

    def test_without_evaluation(self):
        env = _make_envelope()
        result = format_signal_summary(env, None)
        assert "[BTC/USDT]" in result
        assert "ENTRY" in result
        assert "bullish" in result
        assert "Quality:" not in result
        assert "Reason:" not in result

    def test_includes_asset(self):
        env = _make_envelope(asset="ETH/USDT")
        result = format_signal_summary(env)
        assert "[ETH/USDT]" in result

    def test_includes_signal_class(self):
        env = _make_envelope(signal_class=SignalClass.EXIT)
        result = format_signal_summary(env)
        assert "EXIT" in result

    def test_includes_direction(self):
        env = _make_envelope(direction=SignalDirection.BEARISH)
        result = format_signal_summary(env)
        assert "bearish" in result

    def test_includes_confidence(self):
        env = _make_envelope(confidence=0.55)
        result = format_signal_summary(env)
        assert "0.55" in result

    def test_includes_risk_score(self):
        env = _make_envelope(risk_score=0.8)
        result = format_signal_summary(env)
        assert "0.80" in result


class TestEvaluationParts:
    def test_uses_summary_when_present(self):
        env = _make_envelope()
        ev = _make_evaluation(summary="Short bullish signal.")
        result = format_signal_summary(env, ev)
        assert "Short bullish signal." in result
        assert "Quality:" in result

    def test_uses_reasoning_when_summary_empty(self):
        env = _make_envelope()
        ev = _make_evaluation(reasoning="Fallback reasoning text", summary="")
        result = format_signal_summary(env, ev)
        assert "Fallback reasoning text" in result

    def test_shows_quality(self):
        env = _make_envelope()
        ev = _make_evaluation(signal_quality="strong")
        result = format_signal_summary(env, ev)
        assert "Quality: strong" in result

    def test_shows_quality_without_summary_or_reasoning(self):
        env = _make_envelope()
        ev = _make_evaluation(reasoning="", summary="")
        result = format_signal_summary(env, ev)
        assert "Quality:" in result


class TestLengthConstraint:
    def test_under_280_chars_basic(self):
        env = _make_envelope()
        result = format_signal_summary(env)
        assert len(result) <= 280

    def test_under_280_chars_with_evaluation(self):
        env = _make_envelope()
        ev = _make_evaluation(
            summary="A very long summary that might push the total over the 280 character limit "
                    "for notification compatibility, so we need to ensure truncation works properly.",
        )
        result = format_signal_summary(env, ev)
        assert len(result) <= 280

    def test_under_280_chars_with_long_reasoning(self):
        env = _make_envelope()
        # reasoning is max_length=300, so use a long summary instead
        ev = _make_evaluation(
            reasoning="short",
            summary="A" * 400,
        )
        result = format_signal_summary(env, ev)
        assert len(result) <= 280

    def test_long_summary_truncated_with_ellipsis(self):
        env = _make_envelope()
        ev = _make_evaluation(summary="A" * 400)
        result = format_signal_summary(env, ev)
        assert len(result) <= 280
        # Should end with truncated text
        assert result.endswith("…") or len(result) < 280


class TestDifferentSignalTypes:
    def test_exit_signal(self):
        env = _make_envelope(
            signal_class=SignalClass.EXIT,
            direction=SignalDirection.BEARISH,
        )
        result = format_signal_summary(env)
        assert "EXIT" in result
        assert "bearish" in result

    def test_risk_signal(self):
        env = _make_envelope(
            signal_class=SignalClass.RISK,
            direction=SignalDirection.NEUTRAL,
        )
        result = format_signal_summary(env)
        assert "RISK" in result
        assert "neutral" in result

    def test_invalidation_signal(self):
        env = _make_envelope(signal_class=SignalClass.INVALIDATION)
        result = format_signal_summary(env)
        assert "INVALIDATION" in result
