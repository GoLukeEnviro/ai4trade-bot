from __future__ import annotations

import asyncio
import json
import logging
import os
import re
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
    "Always respond with valid JSON only. No markdown, no explanation outside JSON.\n"
    "\n"
    "CAPITAL PRESERVATION DIRECTIVE:\n"
    "Capital preservation is your primary directive. When in doubt, prioritize\n"
    "protecting capital over pursuing gains.\n"
    "\n"
    "ANTI-HALLUCINATION DIRECTIVES:\n"
    "- Never fabricate data, prices, indicators, or market conditions.\n"
    "- If data is incomplete or ambiguous, flag it explicitly — do not guess.\n"
    "- Only reference data explicitly provided in the signal.\n"
    "\n"
    "LEVERAGE AND POSITION-SIZING CAUTION:\n"
    "- Default to no leverage recommendation (suggested_leverage = null).\n"
    "- Conservative position sizing only (suggest small percentages).\n"
    "\n"
    "ADVISORY-ONLY RULES:\n"
    "- Do not recommend direct order execution.\n"
    "- Your output is advisory only — it will never be used as execution authority.\n"
    "- When uncertain, prefer HOLD or lower confidence.\n"
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
    '  "risk_level": "<low|medium|high|extreme>",\n'
    '  "market_regime": "<trending|ranging|volatile|quiet>",\n'
    '  "reasoning": "<max 2 sentences, factual>",\n'
    '  "ai_risk_score": <float 0.0-1.0>,\n'
    '  "signal_quality": "<strong|usable|weak|contradictory>",\n'
    '  "recommended_handling": "<store_only|summary|risk_summary|review_required|suppress>",\n'
    '  "contradictions": [<strings>],\n'
    '  "missing_context": [<strings>],\n'
    '  "summary": "<one-line compact summary, max 120 chars>",\n'
    '  "recommended_action": "<hold|reduce_exposure|wait_for_confirmation>" or null,\n'
    '  "suggested_position_size_pct": <float 0-100 or null>,\n'
    '  "suggested_leverage": <float or null>,\n'
    '  "warnings": [<strings>],\n'
    '  "key_takeaways": [<strings>],\n'
    '  "data_completeness_score": <float 0.0-1.0 or null>,\n'
    '  "confidence_drivers": [<strings>],\n'
    '  "risk_drivers": [<strings>]\n'
    "}}"
)

# Regex to extract JSON from markdown code blocks
_MD_JSON_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)


def _safe_default_evaluation(model_used: str, latency_ms: int) -> AIEvaluation:
    """Return a safe fallback evaluation when LLM response cannot be parsed."""
    return AIEvaluation(
        ai_confidence=0.0,
        risk_level="medium",
        market_regime="quiet",
        reasoning="LLM response could not be parsed; using safe defaults.",
        model_used=model_used,
        evaluation_latency_ms=latency_ms,
        ai_risk_score=0.5,
        signal_quality="weak",
        recommended_handling="store_only",
        contradictions=[],
        missing_context=[],
        summary="",
    )


def _parse_llm_json(raw_content: str) -> dict | None:
    """Try to extract a JSON dict from an LLM response string.

    Strategy:
    1. Direct ``json.loads``.
    2. Extract from markdown code fences (```json ... ```).
    3. Find the first ``{``…``}`` brace-delimited substring.
    4. Give up and return ``None``.
    """
    # 1) Direct parse
    try:
        result = json.loads(raw_content)
        if isinstance(result, dict):
            return result
    except (json.JSONDecodeError, ValueError):
        pass

    # 2) Markdown code-block extraction
    match = _MD_JSON_RE.search(raw_content)
    if match:
        try:
            result = json.loads(match.group(1).strip())
            if isinstance(result, dict):
                return result
        except (json.JSONDecodeError, ValueError):
            pass

    # 3) Brace-delimited extraction (for text wrapping JSON)
    start = raw_content.find("{")
    if start != -1:
        # Find the matching closing brace
        depth = 0
        for i in range(start, len(raw_content)):
            if raw_content[i] == "{":
                depth += 1
            elif raw_content[i] == "}":
                depth -= 1
                if depth == 0:
                    candidate = raw_content[start : i + 1]
                    try:
                        result = json.loads(candidate)
                        if isinstance(result, dict):
                            return result
                    except (json.JSONDecodeError, ValueError):
                        pass
                    break

    return None


def _extract_optional_str(parsed: dict, key: str) -> str | None:
    """Safely extract an optional string from parsed LLM JSON."""
    try:
        value = parsed.get(key)
        if value is None:
            return None
        return str(value)
    except Exception:
        logger.warning("Malformed %s field in LLM response, defaulting to None", key)
        return None


def _extract_optional_float(parsed: dict, key: str) -> float | None:
    """Safely extract an optional float from parsed LLM JSON."""
    try:
        value = parsed.get(key)
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        logger.warning("Malformed %s field in LLM response, defaulting to None", key)
        return None


def _extract_optional_list(parsed: dict, key: str) -> list[str]:
    """Safely extract an optional list of strings from parsed LLM JSON."""
    try:
        value = parsed.get(key)
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        logger.warning("Expected list for %s, got %s; defaulting to []", key, type(value).__name__)
        return []
    except Exception:
        logger.warning("Malformed %s field in LLM response, defaulting to []", key)
        return []


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
        fallback_model: str | None = None,
    ) -> None:
        self._model = model or os.getenv("DEEPSEEK_MODEL", "deepseek-reasoner")
        self._fallback_model = fallback_model
        self._temperature = temperature
        self._timeout = timeout_seconds
        self._threshold = threshold
        self._cache = EvaluationCache(ttl_seconds=cache_ttl_seconds)
        self._client = AsyncOpenAI(
            api_key=api_key or os.environ["DEEPSEEK_API_KEY"],
            base_url=base_url or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            timeout=timeout_seconds,
        )

    async def _call_model(self, model: str, prompt: str) -> str:
        """Call a specific model and return the raw content string."""
        response = await self._client.chat.completions.create(
            model=model,
            temperature=self._temperature,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content or ""

    def _build_evaluation(
        self, parsed: dict, model_used: str, latency_ms: int,
    ) -> AIEvaluation:
        """Construct an AIEvaluation from the parsed LLM dict.

        All new institutional-grade fields use safe extraction helpers
        so that missing or malformed data degrades gracefully rather
        than crashing the runtime.
        """
        return AIEvaluation(
            ai_confidence=float(parsed.get("ai_confidence", 0.0)),
            risk_level=parsed.get("risk_level", "medium"),
            market_regime=parsed.get("market_regime", "quiet"),
            reasoning=str(parsed.get("reasoning", ""))[:300],
            model_used=model_used,
            evaluation_latency_ms=latency_ms,
            ai_risk_score=float(parsed.get("ai_risk_score", 0.5)),
            signal_quality=parsed.get("signal_quality", "usable"),
            recommended_handling=parsed.get("recommended_handling", "store_only"),
            contradictions=parsed.get("contradictions", []),
            missing_context=parsed.get("missing_context", []),
            summary=str(parsed.get("summary", ""))[:120],
            # Institutional-grade fields (Issue #34)
            recommended_action=_extract_optional_str(parsed, "recommended_action"),
            suggested_position_size_pct=_extract_optional_float(parsed, "suggested_position_size_pct"),
            suggested_leverage=_extract_optional_float(parsed, "suggested_leverage"),
            warnings=_extract_optional_list(parsed, "warnings"),
            key_takeaways=_extract_optional_list(parsed, "key_takeaways"),
            data_completeness_score=_extract_optional_float(parsed, "data_completeness_score"),
            confidence_drivers=_extract_optional_list(parsed, "confidence_drivers"),
            risk_drivers=_extract_optional_list(parsed, "risk_drivers"),
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

        # Try primary model, then fallback model on timeout
        models_to_try: list[tuple[str, bool]] = [(self._model, False)]
        if self._fallback_model:
            models_to_try.append((self._fallback_model, True))

        last_model_used = self._model
        for model_name, is_fallback in models_to_try:
            t_start = time.perf_counter()
            try:
                raw_content = await asyncio.wait_for(
                    self._call_model(model_name, prompt),
                    timeout=self._timeout,
                )
                latency_ms = int((time.perf_counter() - t_start) * 1000)

                parsed = _parse_llm_json(raw_content)
                if parsed is not None:
                    evaluation = self._build_evaluation(parsed, model_name, latency_ms)
                else:
                    logger.warning(
                        "Could not parse LLM JSON for %s (model=%s)",
                        signal.asset, model_name,
                    )
                    evaluation = _safe_default_evaluation(model_name, latency_ms)

                await self._cache.set(signal.asset, direction_str, evaluation)
                logger.info(
                    "Evaluated %s: confidence=%.2f risk=%s regime=%s quality=%s latency=%dms%s",
                    signal.asset, evaluation.ai_confidence, evaluation.risk_level,
                    evaluation.market_regime, evaluation.signal_quality, latency_ms,
                    " (fallback)" if is_fallback else "",
                )
                return evaluation

            except asyncio.TimeoutError:
                latency_ms = int((time.perf_counter() - t_start) * 1000)
                last_model_used = model_name
                logger.warning(
                    "LLM timeout for %s (model=%s%s, %.1fs)",
                    signal.asset, model_name,
                    " fallback" if is_fallback else "",
                    self._timeout,
                )
                if is_fallback or not self._fallback_model:
                    # No more models to try — return safe default
                    evaluation = _safe_default_evaluation(model_name, latency_ms)
                    await self._cache.set(signal.asset, direction_str, evaluation)
                    return evaluation
                # else: try fallback model on next iteration
                continue

            except Exception as exc:  # noqa: BLE001
                latency_ms = int((time.perf_counter() - t_start) * 1000)
                logger.warning(
                    "AI evaluation failed for %s (model=%s): %s",
                    signal.asset, model_name, exc,
                )
                if is_fallback or not self._fallback_model:
                    evaluation = _safe_default_evaluation(model_name, latency_ms)
                    await self._cache.set(signal.asset, direction_str, evaluation)
                    return evaluation
                # else: try fallback model on next iteration
                continue

        # Should not reach here, but just in case
        return _safe_default_evaluation(last_model_used, 0)
