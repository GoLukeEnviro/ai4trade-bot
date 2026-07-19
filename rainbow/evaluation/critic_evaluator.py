"""Critic Evaluator — Zweitmeinungs-LLM für kritische Signale (Anti-Manipulation-Filter).

Phase 5 des LLM-Signal-Review-Plans (Issue #91).
Aktiviert nur bei high/critical-Priority-Signalen mit hohem Risk-Score.
Standard: disabled (critic.enabled=false) — Aktivierung nach 2 Wochen Monitoring-Daten.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from typing import TYPE_CHECKING

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from rainbow.evaluation.llm_evaluator import _parse_llm_json, _safe_default_evaluation
from rainbow.evaluation.models import AIEvaluation

if TYPE_CHECKING:
    from rainbow.models.signal import CryptoSignal, Direction

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Trigger-Policy (Issue #91)
# ---------------------------------------------------------------------------

TRIGGER_POLICY: dict = {
    "min_priority": ["high", "critical"],
    "min_risk_score": 0.70,
    "signal_quality_triggers": ["contradictory", "low_confidence_high_risk"],
}

# Mapping von AIEvaluation.risk_level zu Trigger-Prioritäten.
# "extreme" → "critical", "high" → "high", alles andere löst nicht aus.
_RISK_TO_PRIORITY: dict[str, str] = {
    "extreme": "critical",
    "high": "high",
}

# ---------------------------------------------------------------------------
# Critic-spezifischer System-Prompt (skeptischer, adversarialer Blick)
# ---------------------------------------------------------------------------

CRITIC_SYSTEM_PROMPT = (
    "You are a CRITIC evaluator — a second-opinion AI that reviews trading signals\n"
    "that have already been flagged as high-risk by a primary evaluator.\n"
    "Your job is to detect overconfidence, manipulation patterns, and blind spots.\n"
    "\n"
    "CRITIC DIRECTIVES:\n"
    "- Be skeptical. Assume the primary evaluator may have missed something.\n"
    "- Look for contradictions between the signal direction and the technical data.\n"
    "- If the primary confidence seems unjustified, lower it with specific reasoning.\n"
    "- If the direction seems wrong given the data, flag it.\n"
    "- Never fabricate data. Only reference what is provided.\n"
    "\n"
    "Always respond with valid JSON only. No markdown, no explanation outside JSON.\n"
)

CRITIC_USER_PROMPT_TEMPLATE = (
    "REVIEW this high-risk trading signal and its primary evaluation:\n"
    "\n"
    "SIGNAL:\n"
    "- Asset: {asset}\n"
    "- Direction: {direction}\n"
    "- Signal Strength: {strength:.2f}\n"
    "- Rainbow Score: {rainbow_score:.2f}\n"
    "- Source: {source}\n"
    "- Timestamp: {timestamp}\n"
    "- Technical Data: {raw_data_summary}\n"
    "\n"
    "PRIMARY EVALUATION:\n"
    "- AI Confidence: {primary_confidence:.2f}\n"
    "- Risk Level: {primary_risk_level}\n"
    "- Market Regime: {primary_market_regime}\n"
    "- Signal Quality: {primary_signal_quality}\n"
    "- AI Risk Score: {primary_risk_score:.2f}\n"
    "- Reasoning: {primary_reasoning}\n"
    "- Contradictions: {primary_contradictions}\n"
    "- Missing Context: {primary_missing_context}\n"
    "- Warnings: {primary_warnings}\n"
    "\n"
    'Respond ONLY with this JSON structure:\n'
    "{{\n"
    '  "agree_with_primary": <true|false>,\n'
    '  "overridden_confidence": <float 0.0-1.0 or null>,\n'
    '  "overridden_direction": "<bullish|bearish|neutral>" or null,\n'
    '  "critic_reasoning": "<max 2 sentences, factual>",\n'
    '  "critic_risk_score": <float 0.0-1.0>,\n'
    '  "manipulation_suspected": <true|false>,\n'
    '  "blind_spots": [<strings>],\n'
    '  "critic_warnings": [<strings>]\n'
    "}}"
)

# ---------------------------------------------------------------------------
# CriticVerdict — das Ergebnis der Critic-Prüfung
# ---------------------------------------------------------------------------


class CriticVerdict(BaseModel):
    """Ergebnis der Critic-Evaluierung.

    Kann confidence und direction des primären AIEvaluation überschreiben,
    wenn der Critic anderer Meinung ist als der primäre Evaluator.
    """

    triggered: bool = False
    agree_with_primary: bool = True
    overridden_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    overridden_direction: str | None = None  # "bullish" | "bearish" | "neutral"
    critic_reasoning: str = ""
    critic_risk_score: float = Field(default=0.5, ge=0.0, le=1.0)
    manipulation_suspected: bool = False
    blind_spots: list[str] = Field(default_factory=list)
    critic_warnings: list[str] = Field(default_factory=list)
    model_used: str = ""
    evaluation_latency_ms: int = 0


# ---------------------------------------------------------------------------
# CriticEvaluator
# ---------------------------------------------------------------------------


class CriticEvaluator:
    """Zweitmeinungs-LLM-Evaluator für kritische Signale.

    Wrapped den LLMEvaluator und ruft den LLM nur auf, wenn:
    1. critic.enabled=true (default: false)
    2. Das Signal die Trigger-Policy erfüllt (Priority + Risk-Score + Quality)

    Der Critic verwendet einen eigenen, skeptischeren System-Prompt und
    kann confidence sowie direction des primären AIEvaluation überschreiben.
    """

    def __init__(
        self,
        enabled: bool = False,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        temperature: float = 0.1,
        timeout_seconds: float = 5.0,
        trigger_min_priority: list[str] | None = None,
        trigger_min_risk_score: float = 0.70,
        trigger_signal_qualities: list[str] | None = None,
    ) -> None:
        self._enabled = enabled
        self._model = model or os.getenv("DEEPSEEK_MODEL", "deepseek-reasoner")
        self._temperature = temperature
        self._timeout = timeout_seconds

        # Trigger-Konfiguration
        self._trigger_priorities: frozenset[str] = frozenset(
            trigger_min_priority or TRIGGER_POLICY["min_priority"]
        )
        self._trigger_min_risk_score = trigger_min_risk_score
        self._trigger_qualities: frozenset[str] = frozenset(
            trigger_signal_qualities or TRIGGER_POLICY["signal_quality_triggers"]
        )

        self._client = AsyncOpenAI(
            api_key=api_key or os.environ["DEEPSEEK_API_KEY"],
            base_url=base_url or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            timeout=timeout_seconds,
        )

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _check_triggers(self, evaluation: AIEvaluation) -> bool:
        """Prüft, ob die Trigger-Bedingungen für den Critic erfüllt sind.

        Returns True wenn:
        - risk_level auf "high" oder "extreme" mapped (→ priority "high"/"critical")
        - ai_risk_score >= trigger_min_risk_score
        - ODER signal_quality in den trigger-Qualitäten liegt
        """
        priority = _RISK_TO_PRIORITY.get(evaluation.risk_level)
        if priority is None:
            return False
        if priority not in self._trigger_priorities:
            return False

        # Entweder Risk-Score-Schwelle ODER Quality-Trigger
        if evaluation.ai_risk_score >= self._trigger_min_risk_score:
            return True
        if evaluation.signal_quality in self._trigger_qualities:
            return True

        return False

    async def evaluate(
        self, signal: CryptoSignal, primary_evaluation: AIEvaluation | None,
    ) -> CriticVerdict:
        """Führe Critic-Evaluierung durch, falls enabled und Trigger erfüllt.

        Args:
            signal: Das ursprüngliche CryptoSignal.
            primary_evaluation: Die bereits durchgeführte primäre AIEvaluation.

        Returns:
            CriticVerdict mit ggf. überschriebenen Werten.
        """
        if not self._enabled:
            return CriticVerdict(triggered=False)

        if primary_evaluation is None:
            return CriticVerdict(triggered=False)

        if not self._check_triggers(primary_evaluation):
            logger.debug(
                "Critic not triggered for %s (risk=%s, score=%.2f, quality=%s)",
                signal.asset,
                primary_evaluation.risk_level,
                primary_evaluation.ai_risk_score,
                primary_evaluation.signal_quality,
            )
            return CriticVerdict(triggered=False)

        logger.info(
            "Critic triggered for %s (risk=%s, score=%.2f, quality=%s)",
            signal.asset,
            primary_evaluation.risk_level,
            primary_evaluation.ai_risk_score,
            primary_evaluation.signal_quality,
        )

        direction_str = signal.direction.value if signal.direction else "neutral"
        prompt = CRITIC_USER_PROMPT_TEMPLATE.format(
            asset=signal.asset,
            direction=direction_str.upper(),
            strength=signal.strength,
            rainbow_score=signal.rainbow_score or 0.0,
            source=signal.source,
            timestamp=signal.timestamp.isoformat(),
            raw_data_summary=_summarize_raw_data(signal.raw_data),
            primary_confidence=primary_evaluation.ai_confidence,
            primary_risk_level=primary_evaluation.risk_level,
            primary_market_regime=primary_evaluation.market_regime,
            primary_signal_quality=primary_evaluation.signal_quality,
            primary_risk_score=primary_evaluation.ai_risk_score,
            primary_reasoning=primary_evaluation.reasoning,
            primary_contradictions=primary_evaluation.contradictions,
            primary_missing_context=primary_evaluation.missing_context,
            primary_warnings=primary_evaluation.warnings,
        )

        t_start = time.perf_counter()
        try:
            raw_content = await asyncio.wait_for(
                self._call_model(prompt),
                timeout=self._timeout,
            )
            latency_ms = int((time.perf_counter() - t_start) * 1000)

            parsed = _parse_llm_json(raw_content)
            if parsed is not None:
                return self._build_verdict(parsed, latency_ms)
            else:
                logger.warning(
                    "Critic: Could not parse LLM JSON for %s", signal.asset,
                )
                return CriticVerdict(
                    triggered=True,
                    agree_with_primary=True,
                    critic_reasoning="Critic response unparseable; keeping primary evaluation.",
                    model_used=self._model,
                    evaluation_latency_ms=latency_ms,
                )

        except asyncio.TimeoutError:
            latency_ms = int((time.perf_counter() - t_start) * 1000)
            logger.warning("Critic timeout for %s (%.1fs)", signal.asset, self._timeout)
            return CriticVerdict(
                triggered=True,
                agree_with_primary=True,
                critic_reasoning="Critic timed out; keeping primary evaluation.",
                model_used=self._model,
                evaluation_latency_ms=latency_ms,
            )

        except Exception as exc:  # noqa: BLE001
            latency_ms = int((time.perf_counter() - t_start) * 1000)
            logger.warning("Critic evaluation failed for %s: %s", signal.asset, exc)
            return CriticVerdict(
                triggered=True,
                agree_with_primary=True,
                critic_reasoning=f"Critic error; keeping primary evaluation.",
                model_used=self._model,
                evaluation_latency_ms=latency_ms,
            )

    async def _call_model(self, prompt: str) -> str:
        """Ruft das LLM mit dem Critic-System-Prompt auf."""
        response = await self._client.chat.completions.create(
            model=self._model,
            temperature=self._temperature,
            messages=[
                {"role": "system", "content": CRITIC_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content or ""

    def _build_verdict(self, parsed: dict, latency_ms: int) -> CriticVerdict:
        """Baut ein CriticVerdict aus dem geparsten LLM-JSON."""
        agree = bool(parsed.get("agree_with_primary", True))

        overridden_conf = parsed.get("overridden_confidence")
        if overridden_conf is not None:
            try:
                overridden_conf = float(overridden_conf)
                overridden_conf = max(0.0, min(1.0, overridden_conf))
            except (TypeError, ValueError):
                overridden_conf = None

        overridden_dir = parsed.get("overridden_direction")
        if overridden_dir is not None and not isinstance(overridden_dir, str):
            overridden_dir = None
        if isinstance(overridden_dir, str):
            overridden_dir = overridden_dir.lower().strip()
            if overridden_dir not in ("bullish", "bearish", "neutral"):
                overridden_dir = None

        critic_risk = float(parsed.get("critic_risk_score", 0.5))
        critic_risk = max(0.0, min(1.0, critic_risk))

        blind_spots: list[str] = []
        raw_blind = parsed.get("blind_spots", [])
        if isinstance(raw_blind, list):
            blind_spots = [str(b) for b in raw_blind]

        critic_warnings: list[str] = []
        raw_warn = parsed.get("critic_warnings", [])
        if isinstance(raw_warn, list):
            critic_warnings = [str(w) for w in raw_warn]

        return CriticVerdict(
            triggered=True,
            agree_with_primary=agree,
            overridden_confidence=overridden_conf,
            overridden_direction=overridden_dir,
            critic_reasoning=str(parsed.get("critic_reasoning", ""))[:300],
            critic_risk_score=critic_risk,
            manipulation_suspected=bool(parsed.get("manipulation_suspected", False)),
            blind_spots=blind_spots,
            critic_warnings=critic_warnings,
            model_used=self._model,
            evaluation_latency_ms=latency_ms,
        )


# ---------------------------------------------------------------------------
# Hilfsfunktion (analog zu context_enricher.summarize_raw_data,
# aber hier lokal, um keine zirkulären Imports zu riskieren)
# ---------------------------------------------------------------------------


def _summarize_raw_data(raw_data: dict | None) -> str:
    """Komprimierte Zusammenfassung der Rohdaten für den Critic-Prompt."""
    if not raw_data:
        return "none"
    try:
        return json.dumps(raw_data, default=str)
    except (TypeError, ValueError):
        return str(raw_data)[:500]
