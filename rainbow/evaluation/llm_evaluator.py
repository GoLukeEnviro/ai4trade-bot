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

SYSTEM_PROMPT = (
    "You are a crypto trading signal evaluator. Analyze signals objectively.\n"
    "Always respond with valid JSON only. No markdown, no explanation outside JSON."
)

USER_PROMPT_TEMPLATE = (
    "Evaluate this crypto trading signal:\n"
    "- Asset: {asset}\n"
    "- Direction: {direction}\n"
    "- Signal Strength: {strength:.2f}\n"
    "- Rainbow Score: {rainbow_score:.2f}\n"
    "- Source: {source}\n"
    "- Timestamp: {timestamp}\n"
    "- Technical Data: {raw_data_summary}\n"
    "\n"
    'Respond ONLY with this JSON structure:\n'
    "{{\n"
    '  "ai_confidence": <float 0.0-1.0>,\n'
    '  "risk_level": "<low|medium|high>",\n'
    '  "market_regime": "<trending|ranging|volatile|quiet>",\n'
    '  "reasoning": "<max 2 sentences, factual>"\n'
    "}}"
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

    async def evaluate(self, signal: CryptoSignal) -> AIEvaluation | None:
        rainbow_score = signal.rainbow_score or 0.0
        if rainbow_score < self._threshold:
            logger.debug(
                "Skipping %s (score=%.2f < threshold=%.2f)",
                signal.asset, rainbow_score, self._threshold,
            )
            return None

        direction_str = signal.direction.value if signal.direction else "neutral"
        cached = await self._cache.get(signal.asset, direction_str)
        if cached is not None:
            return cached

        prompt = USER_PROMPT_TEMPLATE.format(
            asset=signal.asset,
            direction=direction_str.upper(),
            strength=signal.strength,
            rainbow_score=rainbow_score,
            source=signal.source,
            timestamp=signal.timestamp.isoformat(),
            raw_data_summary=summarize_raw_data(signal.raw_data),
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
            parsed = json.loads(raw_content)
            evaluation = AIEvaluation(
                ai_confidence=float(parsed["ai_confidence"]),
                risk_level=parsed["risk_level"],
                market_regime=parsed["market_regime"],
                reasoning=str(parsed["reasoning"])[:300],
                model_used=self._model,
                evaluation_latency_ms=latency_ms,
            )
            await self._cache.set(signal.asset, direction_str, evaluation)
            logger.info(
                "Evaluated %s: confidence=%.2f risk=%s regime=%s latency=%dms",
                signal.asset, evaluation.ai_confidence, evaluation.risk_level,
                evaluation.market_regime, latency_ms,
            )
            return evaluation
        except Exception as exc:  # noqa: BLE001
            logger.warning("AI evaluation failed for %s: %s", signal.asset, exc)
            return None
