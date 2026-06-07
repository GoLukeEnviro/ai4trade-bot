from __future__ import annotations

import json
import logging
import os
import time
from typing import TYPE_CHECKING

from openai import AsyncOpenAI

from rainbow.evaluation.base import BaseEvaluator
from rainbow.evaluation.cache import EvaluationCache
from rainbow.evaluation.context_enricher import summarize_raw_data
from rainbow.evaluation.models import AIEvaluation

if TYPE_CHECKING:
    from rainbow.models.signal import CryptoSignal

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are an expert crypto trading signal evaluator with deep knowledge of \
market microstructure, risk management, and regime analysis.

## Objective
Provide a conservative, evidence-based evaluation of each trading signal. \
Never hallucinate market data. Only use information provided in the signal.

## Behavioral Rules
- Capital preservation is the top priority.
- If data_completeness < 0.5, recommend "skip" or "wait".
- Max 2% portfolio drawdown per signal.
- No leverage recommendation above 5x without strong confirmation.
- No position size above 10% without multi-source confirmation.
- Consider current regime: bull, bear, ranging, high-volatility, low-liquidity.
- Be explicitly aware of your own uncertainty.
- Never fabricate price levels, indicators, or news.

## Output Format
Respond ONLY with valid JSON — no markdown, no text outside the JSON block.

```json
{
  "signal_id": "<string or null>",
  "symbol": "<string>",
  "timeframe": "<string or null>",
  "direction": "<bullish|bearish|neutral>",
  "overall_confidence": "<float 0.0-1.0>",
  "strength": "<weak|moderate|strong|very_strong>",
  "risk_rating": "<low|medium|high|extreme>",
  "expected_holding_period": "<string or null>",
  "key_takeaways": ["<string>", ...],
  "supporting_factors": ["<string>", ...],
  "conflicting_factors": ["<string>", ...],
  "invalidations": ["<string>", ...],
  "recommended_action": "<enter|wait|skip|reduce_size|hedge|close>",
  "suggested_position_size_pct": "<float 0.0-100.0 or null>",
  "suggested_leverage": "<float 1.0-125.0 or null>",
  "stop_loss_review": "<string or null>",
  "take_profit_review": "<string or null>",
  "risk_reward_assessment": "<string or null>",
  "market_regime_alignment": "<string>",
  "data_completeness_score": "<float 0.0-1.0>",
  "warnings": ["<string>", ...],
  "reasoning_summary": "<string max 500 chars>"
}
```"""

USER_PROMPT_TEMPLATE = """\
Evaluate this crypto trading signal:

- Signal ID: {signal_id_str}
- Asset: {asset}
- Timeframe: {timeframe_str}
- Direction: {direction}
- Signal Strength: {strength:.2f}
- Rainbow Score: {rainbow_score:.2f}
- Source: {source}
- Timestamp: {timestamp}
- Technical Data: {raw_data_summary}
- Stop Loss: {stop_loss_str}
- Take Profit: {take_profit_str}
- Leverage: {leverage_str}

Respond ONLY with valid JSON using the schema defined in the system prompt."""


def _safe_aievaluation(
    model_used: str = "fallback",
    latency_ms: int = 0,
) -> AIEvaluation:
    """Return a safe default AIEvaluation instead of raising or returning None."""
    return AIEvaluation(
        ai_confidence=0.0,
        risk_level="extreme",
        market_regime="unknown",
        reasoning="Evaluation failed — safe fallback",
        model_used=model_used,
        evaluation_latency_ms=latency_ms,
        recommended_action="skip",
        warnings=["Evaluation failed, defaulting to skip"],
    )


class LLMEvaluator(BaseEvaluator):
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        temperature: float = 0.1,
        timeout_seconds: float = 5.0,
        threshold: float = 0.5,
        cache_ttl_seconds: int = 300,
    ) -> None:
        self._model = model or os.getenv("DEEPSEEK_MODEL", "deepseek-reasoner")
        self._temperature = temperature
        self._timeout = timeout_seconds
        self._threshold = threshold
        self._cache = EvaluationCache(ttl_seconds=cache_ttl_seconds)
        self._client = AsyncOpenAI(
            api_key=api_key or os.environ["DEEPSEEK_API_KEY"],
            base_url=base_url or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            timeout=timeout_seconds,
        )

    async def evaluate(
        self,
        signal: CryptoSignal,
        skip_on_low_score: bool = True,
    ) -> AIEvaluation | None:
        rainbow_score = signal.rainbow_score or 0.0
        if skip_on_low_score and rainbow_score < self._threshold:
            logger.debug(
                "Skipping %s (score=%.2f < threshold=%.2f)",
                signal.asset, rainbow_score, self._threshold,
            )
            return None

        direction_str = signal.direction.value if signal.direction else "neutral"
        cached = await self._cache.get(signal.asset, direction_str)
        if cached is not None:
            return cached

        # Resolve optional fields with getattr fallbacks (Task 5A)
        signal_id_str = getattr(signal, "signal_id", "") or ""
        timeframe_str = getattr(signal, "timeframe", None) or "N/A"
        stop_loss_str = str(getattr(signal, "stop_loss", None) or "N/A")
        take_profit_val = getattr(signal, "take_profit", None)
        take_profit_str = str(take_profit_val) if take_profit_val is not None else "N/A"
        leverage_str = str(getattr(signal, "leverage", 1.0))

        prompt = USER_PROMPT_TEMPLATE.format(
            signal_id_str=signal_id_str,
            asset=signal.asset,
            timeframe_str=timeframe_str,
            direction=direction_str.upper(),
            strength=signal.strength,
            rainbow_score=rainbow_score,
            source=signal.source,
            timestamp=signal.timestamp.isoformat(),
            raw_data_summary=summarize_raw_data(signal.raw_data),
            stop_loss_str=stop_loss_str,
            take_profit_str=take_profit_str,
            leverage_str=leverage_str,
        )

        t_start = time.perf_counter()
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                temperature=self._temperature,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            )
            latency_ms = int((time.perf_counter() - t_start) * 1000)
            raw_content = response.choices[0].message.content or ""

            # Task 5B: JSON parser hardening
            try:
                parsed = json.loads(raw_content)
            except json.JSONDecodeError:
                logger.warning(
                    "JSONDecodeError for %s — returning safe fallback", signal.asset,
                )
                return _safe_aievaluation(
                    model_used=self._model,
                    latency_ms=latency_ms,
                )

            # Build AIEvaluation from parsed JSON
            evaluation = self._build_evaluation(parsed, latency_ms)
            await self._cache.set(signal.asset, direction_str, evaluation)
            logger.info(
                "Evaluated %s: confidence=%.2f risk=%s regime=%s latency=%dms",
                signal.asset, evaluation.ai_confidence, evaluation.risk_level,
                evaluation.market_regime, latency_ms,
            )
            return evaluation

        except Exception as exc:  # noqa: BLE001
            latency_ms = int((time.perf_counter() - t_start) * 1000)
            logger.warning("AI evaluation failed for %s: %s", signal.asset, exc)
            # Task 5D: Return safe AIEvaluation instead of None
            return _safe_aievaluation(
                model_used=self._model,
                latency_ms=latency_ms,
            )

    def _build_evaluation(self, parsed: dict, latency_ms: int) -> AIEvaluation:
        """Construct AIEvaluation from parsed JSON with safe defaults."""
        def _get(key: str, default=None):
            return parsed.get(key, default)

        return AIEvaluation(
            ai_confidence=float(_get("overall_confidence", _get("ai_confidence", 0.0))),
            risk_level=_get("risk_rating", _get("risk_level", "high")),
            market_regime=str(_get("market_regime_alignment", _get("market_regime", "unknown"))),
            reasoning=str(_get("reasoning_summary", _get("reasoning", "")))[:500],
            model_used=self._model,
            evaluation_latency_ms=latency_ms,
            signal_id=_get("signal_id"),
            strength=_get("strength"),
            expected_holding_period=_get("expected_holding_period"),
            key_takeaways=_get("key_takeaways", []),
            supporting_factors=_get("supporting_factors", []),
            conflicting_factors=_get("conflicting_factors", []),
            invalidations=_get("invalidations", []),
            recommended_action=_get("recommended_action"),
            suggested_position_size_pct=_get("suggested_position_size_pct"),
            suggested_leverage=_get("suggested_leverage"),
            stop_loss_review=_get("stop_loss_review"),
            take_profit_review=_get("take_profit_review"),
            risk_reward_assessment=_get("risk_reward_assessment"),
            data_completeness_score=_get("data_completeness_score"),
            warnings=_get("warnings", []),
            timeframe=_get("timeframe"),
        )
