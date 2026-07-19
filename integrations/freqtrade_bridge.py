"""Freqtrade signal bridge — read-only advisory consumer.

Bridges canonical signal envelopes from the registry to Freqtrade-compatible
advisory dicts. This module NEVER executes trades, makes HTTP calls, or
accesses exchange APIs. It is a pure read-only consumer of the
CanonicalSignalRegistry.

Safety invariants:
  - can_execute MUST be False (enforced by envelope model, re-checked here)
  - dry_run_only MUST be True (enforced by envelope model, re-checked here)
  - HOLD is always the safe fallback on any error or policy violation
  - Confidence modulation ONLY reduces confidence, never increases it
  - final_confidence MUST be <= raw_confidence (safety assertion)
  - HOLD signal MUST remain HOLD after modulation
  - No secrets in logs or output
  - No network access
"""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.signals.envelope import (
    CanonicalSignalEnvelope,
    DataQualityStatus,
    SignalDirection,
)
from core.signals.registry import CanonicalSignalRegistry

# Graceful import: ConfidenceModulator is optional
try:
    from core.signals.confidence_modulation import (
        ConfidenceBand,
        ConfidenceModulator,
    )

    _MODULATION_AVAILABLE = True
except ImportError:
    ConfidenceModulator = None  # type: ignore[assignment, misc]
    ConfidenceBand = None  # type: ignore[assignment, misc]
    _MODULATION_AVAILABLE = False

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Risk level mapping
# ---------------------------------------------------------------------------

def _risk_level_from_score(risk_score: float) -> str:
    """Map a numeric risk_score (0–1) to a risk_level string.

    The ConfidenceModulator uses string risk levels ('low', 'medium',
    'high', 'extreme') while the envelope uses a numeric risk_score.
    This maps the numeric score to the categorical string.
    """
    if risk_score >= 0.9:
        return "extreme"
    if risk_score >= 0.7:
        return "high"
    if risk_score >= 0.4:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Direction mapping: CanonicalSignalEnvelope → Freqtrade action
# ---------------------------------------------------------------------------

_DIRECTION_MAP: dict[SignalDirection, str] = {
    SignalDirection.BULLISH: "long",
    SignalDirection.BEARISH: "short",
    SignalDirection.NEUTRAL: "flat",
}


def _hold(reason: str) -> dict[str, Any]:
    """Return a safe HOLD advisory dict."""
    return {
        "action": "hold",
        "reason": reason,
        "confidence": 0.0,
        "risk_score": 1.0,
        "source": "freqtrade_bridge",
        "timestamp": datetime.now(UTC).isoformat(),
    }


class FreqtradeBridge:
    """Read-only advisory bridge from CanonicalSignalRegistry to Freqtrade.

    Parameters
    ----------
    registry : CanonicalSignalRegistry
        The canonical signal registry to query. The bridge only reads; it
        never writes or modifies signals.
    confidence_threshold : float
        Minimum confidence (0–1) for a signal to be actionable (default 0.6).
    risk_threshold : float
        Maximum risk_score (0–1) allowed; signals at or above this threshold
        are suppressed to HOLD (default 0.7).
    cache_ttl_seconds : float
        How long to cache advisory results per pair (default 60).
    min_interval_seconds : float
        Minimum wall-clock seconds between advisory calls for the same pair
        to prevent flooding (default 30).
    cache_file : str | None
        Optional path to persist the in-memory cache to JSON. If provided, the
        cache is loaded on startup and saved on each write. If the file is
        missing or corrupted, an empty cache is used (no crash). Default is
        None (no persistence, backward compatible).
    """

    def __init__(
        self,
        registry: CanonicalSignalRegistry,
        *,
        confidence_threshold: float = 0.6,
        risk_threshold: float = 0.7,
        cache_ttl_seconds: float = 60.0,
        min_interval_seconds: float = 30.0,
        use_confidence_modulation: bool = True,
        cache_file: str | None = None,
    ) -> None:
        self._registry = registry
        self.confidence_threshold = confidence_threshold
        self.risk_threshold = risk_threshold
        self.cache_ttl_seconds = cache_ttl_seconds
        self.min_interval_seconds = min_interval_seconds
        self._cache_file = Path(cache_file) if cache_file else None

        # Per-pair caches: {pair: {"result": dict, "time": float}}
        self._cache: dict[str, dict[str, Any]] = {}
        # Per-pair rate-limit timestamps: {pair: float}
        self._last_call_time: dict[str, float] = {}

        # Load cache from file if persistence is enabled
        if self._cache_file is not None:
            self._load_cache_from_file()

        # Confidence modulation — only if available and enabled
        self._modulator: ConfidenceModulator | None = None
        if use_confidence_modulation and _MODULATION_AVAILABLE:
            self._modulator = ConfidenceModulator()
            log.info("Confidence modulation enabled in bridge pipeline")
        else:
            if use_confidence_modulation and not _MODULATION_AVAILABLE:
                log.warning(
                    "ConfidenceModulator not available; "
                    "bridge will use raw confidence"
                )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_latest_signal(self, pair: str) -> dict[str, Any]:
        """Return an advisory signal dict for *pair*.

        This method never raises. On any error it returns a HOLD dict with a
        reason explaining the fallback.

        Returns
        -------
        dict with keys: action, reason, confidence, risk_score, source, timestamp
            action is one of "long", "short", "flat", "hold".
            "hold" is the safe fallback for errors/policy violations;
            "flat" is the mapped NEUTRAL direction.
        """
        try:
            return self._get_latest_signal_inner(pair)
        except Exception as exc:
            log.error("FreqtradeBridge error for pair=%s: %s", pair, exc)
            return _hold(f"bridge_error:{exc!r}")

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _get_latest_signal_inner(self, pair: str) -> dict[str, Any]:
        """Core logic — may raise, wrapped by get_latest_signal."""
        now = time.monotonic()

        # --- Rate limiting ---
        last = self._last_call_time.get(pair)
        if last is not None and now - last < self.min_interval_seconds:
            # Return cached if available, otherwise hold
            cached = self._cache.get(pair)
            if cached and (now - cached["time"]) < self.cache_ttl_seconds:
                return cached["result"]
            return _hold("rate_limited")

        self._last_call_time[pair] = now

        # --- Cache check ---
        cached = self._cache.get(pair)
        if cached and (now - cached["time"]) < self.cache_ttl_seconds:
            return cached["result"]

        # --- Query registry ---
        try:
            envelope = self._registry.get_latest_canonical(pair)
        except Exception as exc:
            log.warning("Registry query failed for pair=%s: %s", pair, exc)
            return _hold(f"registry_error:{exc!r}")

        if envelope is None:
            return self._cache_and_return(pair, _hold("no_signal"))

        result = self._evaluate_envelope(pair, envelope)
        return self._cache_and_return(pair, result)

    def _evaluate_envelope(
        self, pair: str, envelope: CanonicalSignalEnvelope
    ) -> dict[str, Any]:
        """Apply all policy checks to an envelope and return advisory dict."""

        # 1. Safety invariant — can_execute MUST be False
        if envelope.actionability.can_execute is not False:
            log.warning(
                "SAFETY: signal %s has can_execute=True — rejecting",
                envelope.id,
            )
            return _hold("safety_violation_can_execute")

        # 2. Safety invariant — dry_run_only MUST be True
        if envelope.actionability.dry_run_only is not True:
            log.warning(
                "SAFETY: signal %s has dry_run_only=False — rejecting",
                envelope.id,
            )
            return _hold("safety_violation_dry_run_only")

        # 3. Expiry check
        if envelope.valid_until is not None:
            now_utc = datetime.now(UTC)
            if now_utc >= envelope.valid_until:
                return _hold("signal_expired")

        # 4. Data quality check — DEGRADED/STALE/UNAVAILABLE → hold
        if envelope.data_quality.status != DataQualityStatus.OK:
            return _hold(f"data_quality_{envelope.data_quality.status.value}")

        # 5. Confidence threshold check
        if envelope.confidence < self.confidence_threshold:
            return _hold(
                f"low_confidence:{envelope.confidence:.3f}<{self.confidence_threshold}"
            )

        # 6. Risk threshold check
        if envelope.risk_score >= self.risk_threshold:
            return _hold(
                f"high_risk:{envelope.risk_score:.3f}>={self.risk_threshold}"
            )

        # 7. Confidence modulation (between confidence check and direction mapping)
        raw_confidence = envelope.confidence
        final_confidence = raw_confidence
        modulation_reasons: list[str] = []
        confidence_band: str | None = None

        if self._modulator is not None:
            try:
                evaluation_data = self._build_evaluation_data(envelope)
                modulated = self._modulator.modulate(evaluation_data)
                final_confidence = modulated.final_confidence
                modulation_reasons = modulated.confidence_modulation_reason
                confidence_band = modulated.confidence_band.value

                # SAFETY ASSERTION: final_confidence MUST be <= raw_confidence
                if final_confidence > raw_confidence:
                    log.error(
                        "SAFETY: modulation increased confidence "
                        "(final=%.6f > raw=%.6f) for signal %s — "
                        "reverting to raw",
                        final_confidence,
                        raw_confidence,
                        envelope.id,
                    )
                    final_confidence = raw_confidence
                    modulation_reasons.append(
                        "safety_revert: final_confidence exceeded raw"
                    )
                    confidence_band = None

                # If confidence band is BLOCKED → force HOLD
                if modulated.confidence_band == ConfidenceBand.BLOCKED:
                    log.info(
                        "Confidence modulation BLOCKED signal %s "
                        "(raw=%.3f → final=%.3f, reason=%s)",
                        envelope.id,
                        raw_confidence,
                        final_confidence,
                        modulation_reasons,
                    )
                    return {
                        "action": "hold",
                        "reason": "modulation_blocked",
                        "confidence": final_confidence,
                        "risk_score": envelope.risk_score,
                        "source": envelope.source,
                        "timestamp": datetime.now(UTC).isoformat(),
                        "signal_id": envelope.id,
                        "direction": envelope.direction.value,
                        "asset": envelope.asset,
                        "modulation_reasons": modulation_reasons,
                        "confidence_band": confidence_band,
                        "raw_confidence": raw_confidence,
                    }

                log.info(
                    "Confidence modulation for signal %s: "
                    "raw=%.3f → final=%.3f, band=%s, reasons=%s",
                    envelope.id,
                    raw_confidence,
                    final_confidence,
                    confidence_band,
                    modulation_reasons,
                )

            except Exception as exc:
                log.warning(
                    "Confidence modulation failed for signal %s, "
                    "falling back to raw confidence: %s",
                    envelope.id,
                    exc,
                )
                final_confidence = raw_confidence
                modulation_reasons = [f"modulation_error:{exc!r}"]

        # 8. Direction mapping (HOLD stays HOLD after modulation)
        action = _DIRECTION_MAP.get(envelope.direction, "hold")

        result: dict[str, Any] = {
            "action": action,
            "reason": f"signal:{envelope.id}",
            "confidence": final_confidence,
            "risk_score": envelope.risk_score,
            "source": envelope.source,
            "timestamp": datetime.now(UTC).isoformat(),
            "signal_id": envelope.id,
            "direction": envelope.direction.value,
            "asset": envelope.asset,
        }

        # Include modulation metadata when modulation was applied
        if self._modulator is not None:
            result["raw_confidence"] = raw_confidence
            if modulation_reasons:
                result["modulation_reasons"] = modulation_reasons
            if confidence_band is not None:
                result["confidence_band"] = confidence_band

        return result

    @staticmethod
    def _build_evaluation_data(
        envelope: CanonicalSignalEnvelope,
    ) -> dict[str, Any]:
        """Build evaluation-like data dict from an envelope for the modulator.

        The ConfidenceModulator accepts dicts with keys like
        'ai_confidence', 'risk_level', 'warnings', and
        'data_completeness_score'. We map envelope fields to these keys.
        """
        return {
            "ai_confidence": envelope.confidence,
            "risk_level": _risk_level_from_score(envelope.risk_score),
            "warnings": [],
            "data_completeness_score": None,
        }

    def _cache_and_return(self, pair: str, result: dict[str, Any]) -> dict[str, Any]:
        """Store result in cache and return it."""
        self._cache[pair] = {"result": result, "time": time.monotonic()}
        if self._cache_file is not None:
            self._save_cache_to_file()
        return result

    def _save_cache_to_file(self) -> None:
        """Persist the in-memory cache to the configured JSON file.

        Best-effort: logs a warning on failure but never raises.
        Only called when ``self._cache_file`` is not None.
        """
        cache_file = self._cache_file
        assert cache_file is not None  # guaranteed by caller
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = cache_file.with_suffix(".tmp")
            with tmp.open("w", encoding="utf-8") as fh:
                json.dump(self._cache, fh, default=str)
            tmp.replace(cache_file)
        except Exception as exc:
            log.warning("Failed to save cache to %s: %s", cache_file, exc)

    def _load_cache_from_file(self) -> None:
        """Load cache from the configured JSON file into memory.

        If the file is missing, corrupted, or unreadable, the in-memory
        cache remains empty (no crash).
        Only called when ``self._cache_file`` is not None.
        """
        cache_file = self._cache_file
        assert cache_file is not None  # guaranteed by caller
        try:
            if not cache_file.exists():
                log.info("Cache file %s not found; starting with empty cache", cache_file)
                return
            with cache_file.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                self._cache = data
                log.info("Loaded cache from %s (%d entries)", cache_file, len(data))
            else:
                log.warning(
                    "Cache file %s has invalid structure; starting empty",
                    cache_file,
                )
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            log.warning(
                "Failed to load cache from %s; starting empty: %s",
                cache_file,
                exc,
            )
