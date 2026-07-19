# core/notifications/telegram_sink.py
"""Telegram NotificationSink for watchdog alerts.

Sends formatted alerts to a Telegram chat via Bot API.
Graceful degradation: if bot token not configured, silently skips.
"""

import logging
import time
from datetime import UTC, datetime
from html import escape
from typing import Any

import requests

from core.watchdog import WatchdogAlert, WatchdogSeverity

log = logging.getLogger(__name__)

# Emoji mapping for severity
_SEVERITY_EMOJI = {
    WatchdogSeverity.INFO: "ℹ️",
    WatchdogSeverity.WARNING: "⚠️",
    WatchdogSeverity.CRITICAL: "🔴",
}


class TelegramSink:
    """Send watchdog alerts to Telegram.

    Features:
    - Rate limiting per chat (min interval between messages)
    - Formatted messages with severity emoji
    - Graceful degradation when token not configured
    - No secrets in logs
    - Dry-run mode for testing
    """

    def __init__(
        self,
        bot_token: str | None = None,
        chat_id: str | None = None,
        min_interval_seconds: float = 60.0,
        dry_run: bool = False,
        http_timeout: float = 10.0,
    ):
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._min_interval = min_interval_seconds
        self._dry_run = dry_run
        self._http_timeout = http_timeout
        self._last_send_time: float = 0.0
        self._send_count: int = 0
        self._skip_count: int = 0
        self._error_count: int = 0

        if not self._is_configured():
            log.info("TelegramSink: not configured (missing bot_token or chat_id) — alerts will be skipped")

    def _is_configured(self) -> bool:
        return bool(self._bot_token and self._chat_id)

    def send(self, alert: WatchdogAlert) -> None:
        """Send alert to Telegram. Respects rate limiting."""
        if not self._is_configured():
            self._skip_count += 1
            return

        # Rate limiting applies to all sends including dry-run
        now = time.time()
        if now - self._last_send_time < self._min_interval:
            self._skip_count += 1
            log.debug("TelegramSink: rate-limited, skipping alert for %s", alert.component)
            return

        message = self._format_message(alert)

        if self._dry_run:
            log.info("TelegramSink (dry-run): would send to chat %s: %s", self._chat_id, message[:100])
            self._last_send_time = time.time()
            self._send_count += 1
            return

        self._do_send(message)

    def _do_send(self, message: str) -> None:
        """Actually send the message via Telegram Bot API."""
        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        payload: dict[str, Any] = {
            "chat_id": self._chat_id,
            "text": message,
            "parse_mode": "HTML",
        }

        try:
            resp = requests.post(url, json=payload, timeout=self._http_timeout)
            resp.raise_for_status()
            self._last_send_time = time.time()
            self._send_count += 1
            log.debug("TelegramSink: alert sent successfully")
        except requests.RequestException as e:
            self._error_count += 1
            # Never log the bot token or full URL
            log.error(
                "TelegramSink: send failed (status=%s): %s",
                getattr(e.response, "status_code", "N/A") if hasattr(e, "response") else "N/A",
                type(e).__name__,
            )

    @staticmethod
    def _format_message(alert: WatchdogAlert) -> str:
        """Format alert as Telegram HTML message."""
        emoji = _SEVERITY_EMOJI.get(alert.severity, "❓")
        severity_label = alert.severity.value.upper()

        lines = [
            f"{emoji} <b>[{severity_label}]</b> Watchdog Alert",
            f"<b>Component:</b> <code>{escape(str(alert.component))}</code>",
            f"<b>Message:</b> {escape(str(alert.message))}",
        ]

        if alert.details:
            detail_lines = []
            for k, v in alert.details.items():
                detail_lines.append(f"  • {escape(str(k))}: {escape(str(v))}")
            lines.append("<b>Details:</b>")
            lines.extend(detail_lines)

        ts = datetime.fromtimestamp(alert.timestamp, tz=UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
        lines.append(f"<b>Time:</b> {ts}")

        return "\n".join(lines)

    @property
    def stats(self) -> dict[str, int]:
        """Return send statistics."""
        return {
            "sent": self._send_count,
            "skipped": self._skip_count,
            "errors": self._error_count,
        }
