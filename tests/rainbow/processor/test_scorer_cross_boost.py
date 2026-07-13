"""Regression tests for cross-signal confirmation scoring."""

from rainbow.models.signal import CryptoSignal, Direction, SignalType
from rainbow.processor.scorer import RainbowScorer


def _signal(signal_type: SignalType, direction: Direction = Direction.BULLISH) -> CryptoSignal:
    return CryptoSignal(
        source=signal_type.value,
        asset="BTC",
        signal_type=signal_type,
        direction=direction,
        strength=0.8,
        confidence=0.7,
    )


def test_single_technical_signal_has_no_cross_confirmation() -> None:
    signals = [_signal(SignalType.TECHNICAL)]

    assert RainbowScorer._has_cross_confirmation(signals) is False


def test_same_direction_cross_signals_receive_a_boost() -> None:
    scorer = RainbowScorer(cross_signal_boost=1.15)
    single_score = scorer.score([_signal(SignalType.TECHNICAL)])[0].rainbow_score
    confirmed_score = scorer.score(
        [_signal(SignalType.TECHNICAL), _signal(SignalType.SENTIMENT)]
    )[0].rainbow_score

    assert RainbowScorer._has_cross_confirmation(
        [_signal(SignalType.TECHNICAL), _signal(SignalType.SENTIMENT)]
    ) is True
    assert confirmed_score is not None
    assert single_score is not None
    assert confirmed_score > single_score


def test_opposite_direction_signals_do_not_cross_confirm() -> None:
    signals = [
        _signal(SignalType.TECHNICAL, Direction.BULLISH),
        _signal(SignalType.SENTIMENT, Direction.BEARISH),
    ]

    assert RainbowScorer._has_cross_confirmation(signals) is False
