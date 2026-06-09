"""Freqtrade signal bridge — read-only advisory consumer.

Bridges canonical signal envelopes from the registry to Freqtrade-compatible
advisory dicts. This module NEVER executes trades, makes HTTP calls, or
accesses exchange APIs. It is a pure read-only consumer of the
CanonicalSignalRegistry.

Safety invariants:
  - can_execute MUST be False (enforced by envelope model, re-checked here)
  - dry_run_only MUST be True (enforced by envelope model, re-checked here)
  - HOLD is always the safe fallback on any error or policy violation
  - No secrets in logs or output
  - No network access
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import Any

from core.signals.envelope import (
    CanonicalSignalEnvelope,
    DataQualityStatus,
    SignalDirection,
)
from core.signals.registry import CanonicalSignalRegistry

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Direction mapping
# ---------------------------------------------------------------------------

_DIRECTION_MAP: dict[SignalDirection, str] = {
    SignalDirection.BULLISH: "buy",
    SignalDirection.BEARISH: "sell",
    SignalDirection.NEUTRAL: "hold",
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
    """

    def __init__(
        self,
        registry: CanonicalSignalRegistry,
        *,
        confidence_threshold: float = 0.6,
        risk_threshold: float = 0.7,
        cache_ttl_seconds: float = 60.0,
        min_interval_seconds: float = 30.0,
    ) -> None:
        self._registry = registry
        self.confidence_threshold = confidence_threshold
        self.risk_threshold = risk_threshold
        self.cache_ttl_seconds = cache_ttl_seconds
        self.min_interval_seconds = min_interval_seconds

        # Per-pair caches: {pair: {"result": dict, "time": float}}
        self._cache: dict[str, dict[str, Any]] = {}
        # Per-pair rate-limit timestamps: {pair: float}
        self._last_call_time: dict[str, float] = {}

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
            action is one of "buy", "sell", "hold".
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
        last = self._last_call_time.get(pair, 0.0)
        if now - last < self.min_interval_seconds:
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
            rows = self._registry.query_latest(asset=pair, limit=1)
        except Exception as exc:
            log.warning("Registry query failed for pair=%s: %s", pair, exc)
            return _hold(f"registry_error:{exc!r}")

        if not rows:
            return self._cache_and_return(pair, _hold("no_signal"))

        row = rows[0]
        # query_latest returns dicts from _row_to_dict — already parsed envelope JSON
        envelope_data = row

        # Parse envelope
        try:
            envelope = CanonicalSignalEnvelope(**envelope_data)
        except Exception as exc:
            log.warning("Failed to parse envelope for pair=%s: %s", pair, exc)
            return self._cache_and_return(pair, _hold(f"envelope_parse_error:{exc!r}"))

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

        # 7. Direction mapping
        action = _DIRECTION_MAP.get(envelope.direction, "hold")

        return {
            "action": action,
            "reason": f"signal:{envelope.id}",
            "confidence": envelope.confidence,
            "risk_score": envelope.risk_score,
            "source": envelope.source,
            "timestamp": datetime.now(UTC).isoformat(),
            "signal_id": envelope.id,
            "direction": envelope.direction.value,
            "asset": envelope.asset,
        }

    def _cache_and_return(self, pair: str, result: dict[str, Any]) -> dict[str, Any]:
        """Store result in cache and return it."""
        self._cache[pair] = {"result": result, "time": time.monotonic()}
        return result
