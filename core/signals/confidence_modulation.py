"""AI Confidence Modulation — Conservative Advisory Layer (Issue #35).

This module provides a confidence modulation layer that ONLY reduces confidence
based on risk signals, data quality, and uncertainty. It never increases confidence
above the raw LLM value and never turns a HOLD into a BUY/SELL.

It is purely advisory — it does not execute trades, modify signal direction, or
interact with any exchange. The Freqtrade bridge may consume the output later.

Safety guarantees:
  - final_confidence is NEVER higher than raw_confidence
  - High risk_level caps maximum confidence
  - Missing or invalid fields default to conservative values
  - modulate() never raises — all errors produce safe defaults
  - No untyped Any — all types are explicit
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Union

from pydantic import BaseModel, Field

from rainbow.evaluation.models import AIEvaluation

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Risk cap table: maps risk_level → maximum allowed final_confidence
# ---------------------------------------------------------------------------

_RISK_CAPS: dict[str, float] = {
    "extreme": 0.15,
    "high": 0.35,
    "medium": 0.65,
    "low": 1.0,
}

# Default confidence when raw_confidence is None or invalid
_DEFAULT_CONFIDENCE: float = 0.3

# Maximum percentage reduction from warnings (capped at 20%)
_MAX_WARNING_PCT: float = 0.20

# Per-warning reduction percentage
_PER_WARNING_PCT: float = 0.05

# Data completeness threshold below which penalty applies
_DATA_COMPLETENESS_THRESHOLD: float = 0.7

# Penalty for low data completeness
_LOW_DATA_COMPLETENESS_PCT: float = 0.15

# Uncertainty penalty when confidence < 0.5
_UNCERTAINTY_PENALTY_PCT: float = 0.10


class ConfidenceBand(str, Enum):
    """Conservative confidence classification bands."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


class ModulatedConfidence(BaseModel):
    """Output of the confidence modulation layer.

    All fields are populated by the modulator; none are optional to downstream
    consumers (except raw_confidence / uncertainty which may be None when the
    source evaluation had no confidence value).
    """

    raw_confidence: float | None
    uncertainty: float | None
    risk_level: str
    final_confidence: float = Field(ge=0.0, le=1.0)
    confidence_band: ConfidenceBand
    confidence_modulation_reason: list[str] = Field(default_factory=list)
    safety_cap_applied: bool = False
    risk_modifier: float = Field(ge=0.0, le=1.0, default=1.0)


def _confidence_to_band(
    final_confidence: float,
    raw_was_none: bool,
) -> ConfidenceBand:
    """Map a final_confidence value to a ConfidenceBand.

    When the original raw_confidence was None the band is UNKNOWN
    regardless of the computed value.
    """
    if raw_was_none:
        return ConfidenceBand.UNKNOWN
    if final_confidence >= 0.7:
        return ConfidenceBand.HIGH
    if final_confidence >= 0.4:
        return ConfidenceBand.MEDIUM
    if final_confidence >= 0.1:
        return ConfidenceBand.LOW
    return ConfidenceBand.BLOCKED


class ConfidenceModulator:
    """Conservative confidence modulation layer.

    The modulate() method accepts an AIEvaluation (or dict with safe
    extraction) and returns a ModulatedConfidence with a final_confidence
    that is always ≤ the raw_confidence, capped by risk level, and reduced
    by uncertainty, warnings, and data completeness penalties.

    modulate() NEVER raises. All errors produce safe conservative defaults.
    """

    def modulate(
        self,
        evaluation: Union[AIEvaluation, dict],
    ) -> ModulatedConfidence:
        """Modulate the confidence of an AIEvaluation.

        Parameters
        ----------
        evaluation : AIEvaluation | dict
            The source evaluation. Dicts are safely extracted; missing or
            invalid keys default to conservative values.

        Returns
        -------
        ModulatedConfidence
            Conservative, non-inflated confidence with full audit trail.
        """
        try:
            return self._modulate_inner(evaluation)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "ConfidenceModulator error, returning safe defaults: %s", exc,
            )
            return self._safe_default(str(exc))

    # ------------------------------------------------------------------
    # Internal implementation
    # ------------------------------------------------------------------

    def _modulate_inner(
        self,
        evaluation: Union[AIEvaluation, dict],
    ) -> ModulatedConfidence:
        raw_confidence = self._extract_raw_confidence(evaluation)
        risk_level = self._extract_risk_level(evaluation)
        warnings = self._extract_warnings(evaluation)
        data_completeness = self._extract_data_completeness(evaluation)

        reasons: list[str] = []
        raw_was_none = raw_confidence is None

        # Step 1: Establish starting confidence
        if raw_confidence is None:
            confidence = _DEFAULT_CONFIDENCE
            reasons.append(
                f"raw_confidence missing/invalid, defaulting to {_DEFAULT_CONFIDENCE}",
            )
        else:
            confidence = raw_confidence

        # Clamp to [0.0, 1.0] in case of invalid LLM output
        if confidence < 0.0:
            confidence = 0.0
            reasons.append("raw_confidence below 0.0 clamped to 0.0")
        elif confidence > 1.0:
            confidence = 1.0
            reasons.append("raw_confidence above 1.0 clamped to 1.0")

        # Step 2: Risk cap
        risk_cap = _RISK_CAPS.get(risk_level, 0.35)  # default to "high" cap
        safety_cap_applied = confidence > risk_cap
        if safety_cap_applied:
            reasons.append(
                f"risk_level '{risk_level}' caps confidence at {risk_cap}",
            )
            confidence = min(confidence, risk_cap)

        # Step 3: Uncertainty penalty (confidence < 0.5)
        if confidence < 0.5:
            penalty = confidence * _UNCERTAINTY_PENALTY_PCT
            confidence = confidence - penalty
            reasons.append(
                f"uncertainty penalty: confidence<0.5 reduced by "
                f"{_UNCERTAINTY_PENALTY_PCT:.0%} (−{penalty:.4f})",
            )

        # Step 4: Warnings penalty (5% per warning, max 20%)
        if warnings:
            warning_count = len(warnings)
            total_warning_pct = min(
                warning_count * _PER_WARNING_PCT,
                _MAX_WARNING_PCT,
            )
            warning_reduction = confidence * total_warning_pct
            confidence = confidence - warning_reduction
            reasons.append(
                f"warnings penalty: {warning_count} warning(s) reduced by "
                f"{total_warning_pct:.0%} (−{warning_reduction:.4f})",
            )

        # Step 5: Data completeness penalty
        if data_completeness is not None and data_completeness < _DATA_COMPLETENESS_THRESHOLD:
            data_penalty = confidence * _LOW_DATA_COMPLETENESS_PCT
            confidence = confidence - data_penalty
            reasons.append(
                f"data_completeness {data_completeness:.2f} < "
                f"{_DATA_COMPLETENESS_THRESHOLD} reduced by "
                f"{_LOW_DATA_COMPLETENESS_PCT:.0%} (\u2212{data_penalty:.4f})",
            )

        # Step 6: Floor at 0.0
        confidence = max(confidence, 0.0)

        # Step 7: Re-apply risk cap (safety — penalties can't push above cap)
        confidence = min(confidence, risk_cap)

        # Step 8: NEVER exceed raw_confidence
        if raw_confidence is not None and confidence > raw_confidence:
            confidence = raw_confidence
            reasons.append("final_confidence clamped to raw_confidence (never increase)")

        # Compute risk_modifier: ratio of post-risk-cap to pre-risk-cap
        # risk_modifier = 1.0 means no reduction from risk cap
        # risk_modifier < 1.0 means risk cap reduced confidence
        if raw_confidence is not None and raw_confidence > 0.0:
            # How much was lost due to risk cap specifically?
            if raw_confidence > risk_cap:
                risk_modifier = risk_cap / raw_confidence
            else:
                risk_modifier = 1.0
        else:
            # If raw_confidence was None, risk_modifier reflects cap vs default
            risk_modifier = risk_cap / _DEFAULT_CONFIDENCE if _DEFAULT_CONFIDENCE > 0 else 0.0
            risk_modifier = min(risk_modifier, 1.0)

        # Compute uncertainty
        uncertainty: float | None = None
        if raw_confidence is not None:
            uncertainty = 1.0 - raw_confidence

        # Map to confidence band
        band = _confidence_to_band(confidence, raw_was_none)

        return ModulatedConfidence(
            raw_confidence=raw_confidence,
            uncertainty=uncertainty,
            risk_level=risk_level,
            final_confidence=round(confidence, 6),
            confidence_band=band,
            confidence_modulation_reason=reasons,
            safety_cap_applied=safety_cap_applied,
            risk_modifier=round(risk_modifier, 6),
        )

    # ------------------------------------------------------------------
    # Safe extraction helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_raw_confidence(
        evaluation: Union[AIEvaluation, dict],
    ) -> float | None:
        """Safely extract raw_confidence from evaluation."""
        try:
            if isinstance(evaluation, AIEvaluation):
                val = evaluation.ai_confidence
            elif isinstance(evaluation, dict):
                val = evaluation.get("ai_confidence")
            else:
                return None

            if val is None:
                return None
            val = float(val)
            if val < 0.0 or val > 1.0:
                # Out of range — treat as invalid rather than clamping here
                # We'll clamp later in the modulation logic
                return val
            return val
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _extract_risk_level(
        evaluation: Union[AIEvaluation, dict],
    ) -> str:
        """Safely extract risk_level, defaulting to 'high'."""
        try:
            if isinstance(evaluation, AIEvaluation):
                return evaluation.risk_level
            elif isinstance(evaluation, dict):
                val = evaluation.get("risk_level", "high")
                if val in _RISK_CAPS:
                    return val
                # Unknown risk level → conservative default
                return "high"
            return "high"
        except Exception:  # noqa: BLE001
            return "high"

    @staticmethod
    def _extract_warnings(
        evaluation: Union[AIEvaluation, dict],
    ) -> list[str]:
        """Safely extract warnings list, defaulting to empty."""
        try:
            if isinstance(evaluation, AIEvaluation):
                return list(evaluation.warnings)
            elif isinstance(evaluation, dict):
                val = evaluation.get("warnings", [])
                if isinstance(val, list):
                    return [str(item) for item in val]
                return []
            return []
        except Exception:  # noqa: BLE001
            return []

    @staticmethod
    def _extract_data_completeness(
        evaluation: Union[AIEvaluation, dict],
    ) -> float | None:
        """Safely extract data_completeness_score, defaulting to None."""
        try:
            if isinstance(evaluation, AIEvaluation):
                return evaluation.data_completeness_score
            elif isinstance(evaluation, dict):
                val = evaluation.get("data_completeness_score")
                if val is None:
                    return None
                val = float(val)
                if 0.0 <= val <= 1.0:
                    return val
                return None
            return None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_default(reason: str) -> ModulatedConfidence:
        """Return a safe conservative default on any error."""
        return ModulatedConfidence(
            raw_confidence=None,
            uncertainty=None,
            risk_level="high",
            final_confidence=0.0,
            confidence_band=ConfidenceBand.BLOCKED,
            confidence_modulation_reason=[
                f"safe default: {reason}",
                "defaulting to 0.0 confidence (BLOCKED)",
            ],
            safety_cap_applied=True,
            risk_modifier=0.0,
        )
