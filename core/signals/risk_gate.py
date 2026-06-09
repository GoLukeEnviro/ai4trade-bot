"""Risk and data-quality gate for canonical signals."""

from __future__ import annotations

from datetime import UTC, datetime

from core.signals.envelope import (
    CanonicalSignalEnvelope,
    SignalClass,
)

# Classes that bypass the gate entirely
_PASS_THROUGH_CLASSES: frozenset[SignalClass] = frozenset({
    SignalClass.RISK,
    SignalClass.SYSTEM_HEALTH,
    SignalClass.DATA_QUALITY,
})


class RiskGate:
    """Evaluate whether a canonical signal is safe to act on.

    Rules are applied **in order**; the first failing rule short-circuits.
    Signals with class RISK, SYSTEM_HEALTH, or DATA_QUALITY always pass.

    Parameters
    ----------
    max_drawdown_pct : float
        Placeholder for future drawdown guard (not yet wired).
    min_confidence : float
        Minimum confidence (0-1) for a signal to pass.
    stale_threshold_seconds : int
        Maximum age in seconds for a signal to be considered fresh.
        Signals whose ``created_at`` is older than this threshold are
        blocked as stale.  Signals with missing or unparseable timestamps
        degrade safely to stale.
    """

    def __init__(
        self,
        max_drawdown_pct: float = 15.0,
        min_confidence: float = 0.3,
        stale_threshold_seconds: int = 300,
    ) -> None:
        self.max_drawdown_pct = max_drawdown_pct
        self.min_confidence = min_confidence
        self.stale_threshold_seconds = stale_threshold_seconds

    def evaluate(
        self,
        envelope: CanonicalSignalEnvelope,
    ) -> tuple[bool, str, CanonicalSignalEnvelope]:
        """Apply gate rules to *envelope*.

        Returns
        -------
        (approved, reason, modified_envelope)
            *approved* is True when the signal passes all checks.
            *reason* is a machine-readable string.
            *modified_envelope* has updated ``actionability``.
        """
        # Fast path: meta-signals always pass
        if envelope.signal_class in _PASS_THROUGH_CLASSES:
            mod = self._update_actionability(envelope, approved=True)
            return True, "passed_meta_signal", mod

        # Rule 1 — data quality
        if envelope.data_quality.status != "ok":
            mod = self._update_actionability(envelope, approved=False)
            return False, "data_quality_degraded", mod

        # Rule 2 — stale signal
        staleness = self._compute_staleness_seconds(envelope)
        if staleness is None or staleness > self.stale_threshold_seconds:
            mod = self._update_actionability(envelope, approved=False)
            return False, "stale_signal", mod

        # Rule 3 — risk too high
        if envelope.risk_score >= 0.8:
            mod = self._update_actionability(envelope, approved=False)
            return False, "risk_too_high", mod

        # Rule 4 — low confidence
        if envelope.confidence < self.min_confidence:
            mod = self._update_actionability(envelope, approved=False)
            return False, "low_confidence", mod

        # Rule 5 — ENTRY with no direction
        if envelope.signal_class == SignalClass.ENTRY and envelope.direction == "neutral":
            mod = self._update_actionability(envelope, approved=False)
            return False, "entry_no_direction", mod

        # All checks passed
        mod = self._update_actionability(envelope, approved=True)
        return True, "passed", mod

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_staleness_seconds(envelope: CanonicalSignalEnvelope) -> float | None:
        """Return seconds elapsed since *envelope.created_at*, or ``None``
        if the timestamp is missing or unparseable (safe-degrades to stale).
        """
        try:
            created = envelope.created_at
            if created is None:
                return None
            # Ensure offset-aware comparison
            if created.tzinfo is None:
                created = created.replace(tzinfo=UTC)
            now = datetime.now(UTC)
            delta = now - created
            return delta.total_seconds()
        except (TypeError, ValueError, AttributeError):
            return None

    @staticmethod
    def _update_actionability(
        envelope: CanonicalSignalEnvelope,
        *,
        approved: bool,
    ) -> CanonicalSignalEnvelope:
        """Return a copy of *envelope* with updated actionability."""
        data = envelope.model_dump()
        data["actionability"] = {
            "can_alert": approved,
            "can_execute": False,
            "dry_run_only": True,
        }
        return CanonicalSignalEnvelope(**data)
