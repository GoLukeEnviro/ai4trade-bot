"""Core ingestion logic — maps external signals into canonical envelopes.

This module is *data-only*: it stores signals but never triggers execution.
All ingested envelopes are marked ``can_execute=False`` and ``dry_run_only=True``
(safety invariants enforced by ``Actionability._enforce_safety``).
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from threading import Lock

from core.signals.envelope import (
    Actionability,
    CanonicalSignalEnvelope,
    DataQuality,
    DataQualityStatus,
    SignalClass,
    SignalDirection,
    SignalPriority,
)
from core.signals.registry import CanonicalSignalRegistry
from core.signals.risk_gate import RiskGate
from rainbow.ingest.models import RainbowIngestRequest, RainbowIngestResult

log = logging.getLogger("rainbow.ingest")

# ---------------------------------------------------------------------------
# Simple per-source rate limiter
# ---------------------------------------------------------------------------

class _PerSourceRateLimiter:
    """Track request counts per source within a sliding 60-second window.

    Thread-safe.  Not meant to be a production-grade solution — just a
    guard against runaway producers.
    """

    def __init__(self, max_per_minute: int = 60, window_seconds: int = 60) -> None:
        self._max = max_per_minute
        self._window = window_seconds
        self._counts: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def allow(self, source: str) -> bool:
        """Return True if *source* is within rate, False otherwise."""
        now = time.monotonic()
        cutoff = now - self._window
        with self._lock:
            timestamps = self._counts[source]
            # Evict expired entries
            self._counts[source] = [t for t in timestamps if t > cutoff]
            if len(self._counts[source]) >= self._max:
                return False
            self._counts[source].append(now)
            return True


# ---------------------------------------------------------------------------
# RainbowIngestor
# ---------------------------------------------------------------------------

class RainbowIngestor:
    """Accept a :class:`RainbowIngestRequest` and persist it as a canonical signal.

    The ingestor NEVER raises — all failures are surfaced via the
    ``status="error"`` result.
    """

    def __init__(
        self,
        registry: CanonicalSignalRegistry,
        risk_gate: RiskGate | None = None,
        rate_limit_per_minute: int = 60,
    ) -> None:
        self._registry = registry
        self._risk_gate = risk_gate or RiskGate()
        self._rate_limiter = _PerSourceRateLimiter(max_per_minute=rate_limit_per_minute)

    def ingest(self, request: RainbowIngestRequest) -> RainbowIngestResult:
        """Process *request* and return a structured result.

        The happy path:
        1. Check rate limit.
        2. Map request → ``CanonicalSignalEnvelope``.
        3. Run through ``RiskGate``.
        4. Persist via ``CanonicalSignalRegistry.append()``.
        5. Return ``accepted`` / ``rejected``.
        Any exception → ``error`` with reason (never re-raised).
        """
        try:
            # --- Rate limit check ---
            if not self._rate_limiter.allow(request.source):
                return RainbowIngestResult(
                    status="rejected",
                    reason=f"rate_limit_exceeded for source '{request.source}'",
                )

            # --- Build envelope ---
            envelope = self._request_to_envelope(request)

            # --- Risk gate ---
            approved, gate_reason, mod_envelope = self._risk_gate.evaluate(envelope)

            # --- Persist ---
            signal_id = self._registry.append(mod_envelope)

            status: str = "accepted" if approved else "rejected"
            log.info(
                "ingest %s signal_id=%s asset=%s source=%s gate=%s",
                status,
                signal_id,
                request.asset,
                request.source,
                gate_reason,
            )

            return RainbowIngestResult(
                status=status,  # type: ignore[arg-type]
                signal_id=signal_id,
                reason=gate_reason,
                envelope_created=True,
            )

        except Exception as exc:
            log.error("ingest error: %s", exc)
            return RainbowIngestResult(
                status="error",
                reason=str(exc),
            )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _request_to_envelope(request: RainbowIngestRequest) -> CanonicalSignalEnvelope:
        """Map a :class:`RainbowIngestRequest` to a :class:`CanonicalSignalEnvelope`."""
        from datetime import UTC, datetime

        direction_map = {
            "bullish": SignalDirection.BULLISH,
            "bearish": SignalDirection.BEARISH,
            "neutral": SignalDirection.NEUTRAL,
        }
        direction = direction_map.get(request.direction, SignalDirection.NEUTRAL)

        # Parse timestamp
        try:
            created_at = datetime.fromisoformat(request.timestamp)
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=UTC)
        except (ValueError, TypeError):
            created_at = datetime.now(UTC)

        # Determine signal class
        sig_class = SignalClass.ENTRY
        if request.signal_class is not None:
            try:
                sig_class = SignalClass(request.signal_class.lower())
            except ValueError:
                sig_class = SignalClass.ENTRY

        # Confidence — fall back to strength when not provided
        confidence = request.confidence if request.confidence is not None else request.strength

        # Risk score default to 0.5 (neutral) for externally ingested signals
        risk_score = 0.5

        return CanonicalSignalEnvelope(
            signal_class=sig_class,
            subtype="rainbow_ingest",
            source=f"rainbow_ingest:{request.source}",
            asset=request.asset,
            created_at=created_at,
            direction=direction,
            confidence=confidence,
            risk_score=risk_score,
            priority=SignalPriority.MEDIUM,
            reason_codes=["rainbow_api_ingest"],
            features={
                "strength": request.strength,
                "rainbow_score": request.rainbow_score,
                "raw_data": request.raw_data or {},
            },
            data_quality=DataQuality(
                status=DataQualityStatus.OK,
                source_latency_ms=None,
                source_quality=None,
                freshness_seconds=None,
            ),
            actionability=Actionability(can_alert=True),
            invalidation={"max_age_seconds": 3600, "conditions": []},
            raw_refs=[],
        )
