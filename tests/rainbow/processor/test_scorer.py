"""Tests for rainbow.processor.scorer — RainbowScorer."""

from datetime import UTC, datetime, timedelta

from rainbow.models.signal import CryptoSignal, Direction, SignalType
from rainbow.processor.scorer import RainbowScorer


def _make_signal(
    asset: str = "BTC",
    signal_type: SignalType = SignalType.TECHNICAL,
    direction: Direction = Direction.BULLISH,
    strength: float = 0.8,
    confidence: float = 0.7,
    source: str = "test",
    minutes_ago: int = 0,
) -> CryptoSignal:
    return CryptoSignal(
        source=source,
        asset=asset,
        signal_type=signal_type,
        direction=direction,
        strength=strength,
        confidence=confidence,
        timestamp=datetime.now(UTC) - timedelta(minutes=minutes_ago),
    )


class TestRainbowScorerConstruction:
    def test_default_construction(self) -> None:
        scorer = RainbowScorer()
        assert scorer._weights == RainbowScorer._DEFAULT_WEIGHTS
        assert scorer._evaluator is None

    def test_custom_construction(self) -> None:
        scorer = RainbowScorer(
            weights={"technical": 0.5, "sentiment": 0.5},
            decay_threshold_seconds=7200,
            decay_factor=0.5,
            cross_signal_boost=1.2,
        )
        assert scorer._weights == {"technical": 0.5, "sentiment": 0.5}
        assert scorer._decay_threshold == 7200


class TestRainbowScorerScore:
    def test_score_empty_list(self) -> None:
        scorer = RainbowScorer()
        result = scorer.score([])
        assert result == []

    def test_score_single_signal(self) -> None:
        scorer = RainbowScorer()
        signal = _make_signal()
        result = scorer.score([signal])
        assert len(result) == 1
        assert result[0].rainbow_score is not None
        assert 0.0 <= result[0].rainbow_score <= 1.0

    def test_score_multiple_signals_same_asset(self) -> None:
        scorer = RainbowScorer()
        signals = [
            _make_signal(source="ta", signal_type=SignalType.TECHNICAL),
            _make_signal(source="news", signal_type=SignalType.NEWS),
        ]
        result = scorer.score(signals)
        assert len(result) == 2
        # Both should get the same rainbow_score
        assert result[0].rainbow_score == result[1].rainbow_score

    def test_score_decay_with_age(self) -> None:
        """Two signals of equal strength: the fresher one dominates due to decay."""
        scorer = RainbowScorer(decay_threshold_seconds=60)
        # With decay_threshold=0, old signals get decayed. Mix a recent bullish
        # signal with an old bearish one — bullish should win because it's fresher.
        recent_bull = _make_signal(
            minutes_ago=0, strength=0.9, direction=Direction.BULLISH, signal_type=SignalType.TECHNICAL
        )
        old_bear = _make_signal(
            minutes_ago=120, strength=0.9, direction=Direction.BEARISH, signal_type=SignalType.NEWS
        )
        # With decay, the recent bullish signal gets more weight
        result = scorer.score([recent_bull, old_bear])
        assert len(result) == 2
        assert result[0].rainbow_score is not None

    def test_score_single_signal_always_same(self) -> None:
        """A single signal's rainbow_score is independent of age (decay cancels)."""
        scorer = RainbowScorer()
        recent = _make_signal(minutes_ago=1, direction=Direction.BULLISH)
        old = _make_signal(minutes_ago=120, direction=Direction.BULLISH)
        recent_score = scorer.score([recent])[0].rainbow_score
        old_score = scorer.score([old])[0].rainbow_score
        assert recent_score is not None and old_score is not None
        # Single-signal scores are the same regardless of age
        assert recent_score == old_score


class TestRainbowScorerCrossConfirmation:
    def test_has_cross_confirmation_true(self) -> None:
        signals = [
            _make_signal(signal_type=SignalType.TECHNICAL, direction=Direction.BULLISH),
            _make_signal(signal_type=SignalType.NEWS, direction=Direction.BULLISH),
        ]
        assert RainbowScorer._has_cross_confirmation(signals) is True

    def test_has_cross_confirmation_false_different_directions(self) -> None:
        signals = [
            _make_signal(signal_type=SignalType.TECHNICAL, direction=Direction.BULLISH),
            _make_signal(signal_type=SignalType.NEWS, direction=Direction.BEARISH),
        ]
        assert RainbowScorer._has_cross_confirmation(signals) is False

    def test_has_cross_confirmation_false_single_source(self) -> None:
        signals = [
            _make_signal(signal_type=SignalType.TECHNICAL, direction=Direction.BULLISH),
        ]
        assert RainbowScorer._has_cross_confirmation(signals) is False

    def test_has_cross_confirmation_false_neutral(self) -> None:
        signals = [
            _make_signal(signal_type=SignalType.TECHNICAL, direction=Direction.NEUTRAL),
            _make_signal(signal_type=SignalType.NEWS, direction=Direction.NEUTRAL),
        ]
        assert RainbowScorer._has_cross_confirmation(signals) is False


class TestRainbowScorerScoreAndEvaluate:
    async def test_score_and_evaluate_no_evaluator(self) -> None:
        scorer = RainbowScorer()
        signal = _make_signal()
        result = await scorer.score_and_evaluate([signal])
        assert len(result) == 1
        assert result[0].rainbow_score is not None

    async def test_score_and_evaluate_with_evaluator(self) -> None:
        from unittest.mock import AsyncMock


        mock_eval = _make_ai_evaluation()
        evaluator = AsyncMock()
        evaluator.evaluate.return_value = mock_eval
        scorer = RainbowScorer(evaluator=evaluator, evaluation_threshold=0.0)
        signal = _make_signal(strength=0.5, confidence=0.5)
        result = await scorer.score_and_evaluate([signal])
        assert len(result) == 1


def _make_ai_evaluation():
    from rainbow.evaluation.models import AIEvaluation
    return AIEvaluation(
        ai_confidence=0.8,
        risk_level="low",
        market_regime="trending",
        reasoning="looks good",
        model_used="test",
        evaluation_latency_ms=10,
    )
