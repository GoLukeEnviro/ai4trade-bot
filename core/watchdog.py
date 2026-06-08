# core/watchdog.py
"""Lightweight watchdog for monitoring heartbeat files.

Detects:
- Missing heartbeat files
- Stale heartbeats (too old)
- Malformed heartbeat files

Features:
- Per-component cooldown to prevent spam
- Safe notification abstraction (no direct Telegram/API dependency)
- Synchronous and async-friendly design
"""

import json
import logging
import time
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Protocol

log = logging.getLogger(__name__)


class WatchdogSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class WatchdogAlert:
    """A single watchdog alert."""

    component: str
    severity: WatchdogSeverity
    message: str
    timestamp: float = field(default_factory=time.time)
    details: dict = field(default_factory=dict)


class NotificationSink(Protocol):
    """Protocol for notification sinks — implement this to send alerts anywhere."""

    def send(self, alert: WatchdogAlert) -> None: ...


class LogNotificationSink:
    """Default sink: logs the alert."""

    def send(self, alert: WatchdogAlert) -> None:
        msg = f"[WATCHDOG] {alert.severity.value.upper()} | {alert.component}: {alert.message}"
        if alert.severity == WatchdogSeverity.CRITICAL:
            log.error(msg)
        elif alert.severity == WatchdogSeverity.WARNING:
            log.warning(msg)
        else:
            log.info(msg)


@dataclass
class WatchedComponent:
    """Configuration for a watched component."""

    name: str
    heartbeat_path: str | Path
    stale_threshold_seconds: float = 120.0
    cooldown_seconds: float = 300.0  # 5 minutes between repeated alerts


class Watchdog:
    """Monitors heartbeat files for health."""

    def __init__(
        self,
        components: list[WatchedComponent],
        sinks: list[NotificationSink] | None = None,
    ):
        self._components = components
        self._sinks: list[NotificationSink] = sinks or [LogNotificationSink()]
        self._last_alert_time: dict[str, float] = {}  # component -> last alert timestamp
        self._alert_history: list[WatchdogAlert] = []

    def check_all(self) -> list[WatchdogAlert]:
        """Check all components and return new alerts."""
        alerts: list[WatchdogAlert] = []
        for comp in self._components:
            alert = self._check_component(comp)
            if alert is not None:
                alerts.append(alert)
        return alerts

    def _check_component(self, comp: WatchedComponent) -> WatchdogAlert | None:
        """Check a single component. Returns alert or None."""
        path = Path(comp.heartbeat_path)

        # Check 1: missing
        if not path.exists():
            return self._maybe_alert(
                comp, WatchdogSeverity.CRITICAL, f"Heartbeat file missing: {path}"
            )

        # Check 2: parse
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            return self._maybe_alert(
                comp, WatchdogSeverity.CRITICAL, f"Heartbeat malformed: {e}", details={"error": str(e)}
            )

        if not isinstance(data, dict) or "timestamp_unix" not in data:
            return self._maybe_alert(
                comp,
                WatchdogSeverity.CRITICAL,
                "Heartbeat missing required 'timestamp_unix' field",
                details={"keys": list(data.keys()) if isinstance(data, dict) else []},
            )

        # Check 3: stale
        age = time.time() - data.get("timestamp_unix", 0)
        if age > comp.stale_threshold_seconds:
            return self._maybe_alert(
                comp,
                WatchdogSeverity.WARNING,
                f"Heartbeat stale ({age:.0f}s old, threshold={comp.stale_threshold_seconds:.0f}s)",
                details={"age_seconds": round(age, 1), "threshold": comp.stale_threshold_seconds},
            )

        # Check 4: status
        status = data.get("status", "unknown")
        if status not in ("healthy", "running"):
            return self._maybe_alert(
                comp, WatchdogSeverity.WARNING, f"Unhealthy status: {status}", details={"status": status}
            )

        # All good
        return None

    def _maybe_alert(
        self,
        comp: WatchedComponent,
        severity: WatchdogSeverity,
        message: str,
        details: dict | None = None,
    ) -> WatchdogAlert | None:
        """Create alert only if cooldown has passed."""
        now = time.time()
        last = self._last_alert_time.get(comp.name, 0)

        if now - last < comp.cooldown_seconds:
            log.debug("Watchdog alert suppressed (cooldown): %s", comp.name)
            return None

        alert = WatchdogAlert(
            component=comp.name,
            severity=severity,
            message=message,
            timestamp=now,
            details=details or {},
        )

        self._last_alert_time[comp.name] = now
        self._alert_history.append(alert)

        # Send to all sinks
        for sink in self._sinks:
            try:
                sink.send(alert)
            except Exception as e:
                log.error("Notification sink error: %s", e)

        return alert

    @property
    def alert_history(self) -> list[WatchdogAlert]:
        return list(self._alert_history)

    def clear_history(self) -> None:
        self._alert_history.clear()
