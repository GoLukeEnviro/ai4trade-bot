"""Notification rule checker for canonical signal envelopes."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rainbow.evaluation.models import AIEvaluation

from core.signals.envelope import CanonicalSignalEnvelope, SignalClass, SignalPriority

# Minimum seconds between repeated notifications for the same (asset, class) pair.
_COOLDOWN_SECONDS = 300

# Meta-signal classes that warrant notification at high+ priority.
_META_CLASSES: frozenset[SignalClass] = frozenset(
    {SignalClass.RISK, SignalClass.SYSTEM_HEALTH, SignalClass.DATA_QUALITY}
)


class NotificationRuleChecker:
    """Stateless-ish rule engine that decides whether a signal should trigger a
    notification.

    The only mutable state is an in-memory cooldown dict tracking the last
    notification timestamp per ``(asset, signal_class)`` pair.
    """

    def __init__(self, cooldown_seconds: float = _COOLDOWN_SECONDS) -> None:
        self._cooldown_seconds = cooldown_seconds
        self._last_notification: dict[tuple[str, str], float] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def should_notify(
        self,
        envelope: CanonicalSignalEnvelope,
        evaluation: AIEvaluation | None = None,
    ) -> tuple[bool, str]:
        """Return ``(should_notify, reason)``.

        Evaluation is accepted for future rule expansion but not required.
        """
        asset = envelope.asset
        sig_class = envelope.signal_class
        priority = envelope.priority
        key = (asset, sig_class.value)

        # --- Rule 1: critical priority always notifies ---
        if priority == SignalPriority.CRITICAL:
            return self._check_cooldown(key, "critical_priority")

        # --- Rule 2: meta class + high/critical ---
        if sig_class in _META_CLASSES and priority in (
            SignalPriority.HIGH,
            SignalPriority.CRITICAL,
        ):
            return self._check_cooldown(key, "meta_high_priority")

        # --- Rule 3: ENTRY with high confidence and low risk ---
        if (
            sig_class == SignalClass.ENTRY
            and envelope.confidence >= 0.7
            and envelope.risk_score < 0.6
        ):
            return self._check_cooldown(key, "high_confidence_low_risk_entry")

        # --- Rule 4: everything else → don't notify ---
        return False, "no_rule_matched"

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _check_cooldown(self, key: tuple[str, str], reason: str) -> tuple[bool, str]:
        """Return ``(True, reason)`` if cooldown has elapsed, else ``(False, …)``."""
        now = time.monotonic()
        last = self._last_notification.get(key, 0.0)
        if now - last < self._cooldown_seconds:
            return False, f"cooldown_active ({reason})"
        self._last_notification[key] = now
        return True, reason
