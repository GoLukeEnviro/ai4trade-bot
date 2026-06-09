"""Tests for rainbow.evaluation.base — BaseEvaluator ABC."""

import pytest

from rainbow.evaluation.base import BaseEvaluator
from rainbow.models.signal import CryptoSignal, Direction, SignalType


class TestBaseEvaluatorABC:
    """BaseEvaluator is abstract; it cannot be instantiated directly."""

    def test_cannot_instantiate_directly(self) -> None:
        with pytest.raises(TypeError, match="abstract method"):
            BaseEvaluator()  # type: ignore[abstract]

    def test_concrete_subclass_instantiation(self) -> None:
        class StubEvaluator(BaseEvaluator):
            async def evaluate(self, signal: CryptoSignal):
                return None

        evaluator = StubEvaluator()
        assert evaluator is not None

    async def test_evaluate_returns_none(self) -> None:
        class StubEvaluator(BaseEvaluator):
            async def evaluate(self, signal: CryptoSignal):
                return None

        evaluator = StubEvaluator()
        signal = CryptoSignal(
            source="test",
            asset="BTC",
            signal_type=SignalType.TECHNICAL,
            direction=Direction.BULLISH,
            strength=0.8,
            confidence=0.7,
        )
        result = await evaluator.evaluate(signal)
        assert result is None

    def test_missing_evaluate_raises_type_error(self) -> None:
        class IncompleteEvaluator(BaseEvaluator):
            pass

        with pytest.raises(TypeError):
            IncompleteEvaluator()  # type: ignore[abstract]
