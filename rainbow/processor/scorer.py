from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from rainbow.models.signal import CryptoSignal, Direction

if TYPE_CHECKING:
    from rainbow.evaluation.llm_evaluator import LLMEvaluator

logger = logging.getLogger(__name__)


class RainbowScorer:
    _DEFAULT_WEIGHTS: dict[str, float] = {
        "technical": 0.4,
        "sentiment": 0.3,
        "social": 0.2,
        "news": 0.1,
    }

    _DIRECTION_MULTIPLIER: dict[str, float] = {
        "bullish": 1.0,
        "neutral": 0.5,
        "bearish": 0.0,
    }

    _DECAY_THRESHOLD_SECONDS = 3600
    _DECAY_FACTOR = 0.7
    _CROSS_SIGNAL_BOOST = 1.15

    def __init__(
        self,
        weights: dict[str, float] | None = None,
        decay_threshold_seconds: int = 3600,
        decay_factor: float = 0.7,
        cross_signal_boost: float = 1.15,
        evaluator: LLMEvaluator | None = None,
        evaluation_threshold: float = 0.5,
        xgboost_scorer: Any | None = None,
    ):
        self._weights = weights or self._DEFAULT_WEIGHTS
        self._decay_threshold = decay_threshold_seconds
        self._decay_factor = decay_factor
        self._cross_signal_boost = cross_signal_boost
        self._evaluator = evaluator
        self._evaluation_threshold = evaluation_threshold
        if xgboost_scorer is None:
            from rainbow.processor.xgboost_scorer import XGBoostSignalScorer

            xgboost_scorer = XGBoostSignalScorer()
        self._xgboost_scorer = xgboost_scorer

    def score(self, signals: list[CryptoSignal]) -> list[CryptoSignal]:
        """Berechne rainbow_score fuer eine Gruppe von Signalen desselben Assets."""
        if not signals:
            return signals

        rainbow_score = self._compute_rainbow_score(signals)
        return [
            sig.model_copy(update={"rainbow_score": self._ml_score(sig, rainbow_score)})
            for sig in signals
        ]

    def _ml_score(self, signal: CryptoSignal, fallback_score: float) -> float:
        """Use a persisted model when present; retain deterministic scoring otherwise."""
        try:
            from core.signals.adapters import from_rainbow_signal

            model_score = self._xgboost_scorer.score(from_rainbow_signal(signal))
        except Exception as exc:
            logger.warning("XGBoost scoring failed for %s: %s", signal.asset, exc)
            return fallback_score
        return fallback_score if model_score is None else model_score

    async def score_and_evaluate(self, signals: list[CryptoSignal]) -> list[CryptoSignal]:
        """Score + optionale KI-Evaluierung. Async Wrapper fuer die Pipeline."""
        scored = self.score(signals)
        if not self._evaluator:
            return scored

        results = await asyncio.gather(
            *[self._evaluate_single(sig) for sig in scored],
            return_exceptions=True,
        )
        evaluated: list[CryptoSignal] = []
        for i, result in enumerate(results):
            if isinstance(result, CryptoSignal):
                evaluated.append(result)
            else:
                if isinstance(result, Exception):
                    logger.warning("Evaluation failed for %s: %s", scored[i].asset, result)
                evaluated.append(scored[i])
        return evaluated

    async def _evaluate_single(self, signal: CryptoSignal) -> CryptoSignal:
        if (signal.rainbow_score or 0.0) < self._evaluation_threshold:
            return signal
        evaluation = await self._evaluator.evaluate(signal)
        return signal.model_copy(update={"ai_evaluation": evaluation})

    def _compute_rainbow_score(self, signals: list[CryptoSignal]) -> float:
        now = datetime.now(UTC)
        weighted_sum = 0.0
        total_weight = 0.0

        for sig in signals:
            type_key = sig.signal_type.value
            base_weight = self._weights.get(type_key, 0.1)

            age_seconds = (now - sig.timestamp).total_seconds()
            decay_periods = max(0, age_seconds - self._decay_threshold) / self._decay_threshold
            decay = self._decay_factor ** decay_periods
            weight = base_weight * (1.0 if decay_periods <= 0 else decay)

            direction_value = sig.direction.value if sig.direction else "neutral"
            multiplier = self._DIRECTION_MULTIPLIER.get(direction_value, 0.5)

            weighted_sum += sig.strength * multiplier * weight
            total_weight += weight

        if total_weight <= 0:
            return 0.0

        base_score = weighted_sum / total_weight

        boost = self._cross_signal_boost if self._has_cross_confirmation(signals) else 1.0

        return round(min(1.0, base_score * boost), 3)

    @staticmethod
    def _has_cross_confirmation(signals: list[CryptoSignal]) -> bool:
        """True wenn mindestens 2 verschiedene Quellen in dieselbe Richtung zeigen."""
        directions_by_type: dict[str, Direction] = {}
        for sig in signals:
            if sig.direction and sig.direction != Direction.NEUTRAL:
                directions_by_type[sig.signal_type.value] = sig.direction

        if len(directions_by_type) < 2:
            return False

        unique_directions = set(directions_by_type.values())
        return len(unique_directions) == 1
