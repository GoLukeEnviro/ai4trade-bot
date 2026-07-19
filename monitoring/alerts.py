"""Monitoring alert helpers."""

from __future__ import annotations

import time
from html import escape
from typing import Any

import httpx

from core.signals.envelope import CanonicalSignalEnvelope, SignalPriority

# Emoji-Mapping für unterstützte Signal-Prioritäten.
_PRIORITY_EMOJI: dict[SignalPriority, str] = {
    SignalPriority.CRITICAL: "🔴",
    SignalPriority.HIGH: "🟠",
}


class TelegramSignalAlert:
    """Compact Telegram-Alert für Canonical-Signal-Summaries.

    Regeln:
      * Nur Signale mit ``priority in ("high", "critical")`` werden gesendet.
      * Pro Asset gilt ein Cooldown von ``COOLDOWN_SECONDS`` (Default 300s / 5 Min).
      * Cooldown ist per Asset, nicht global — verschiedene Assets können
        unabhängig voneinander alarmieren.
    """

    COOLDOWN_SECONDS: int = 300

    def __init__(
        self,
        bot_token: str | None = None,
        chat_id: str | None = None,
        cooldown_seconds: float | None = None,
        http_timeout: float = 10.0,
    ) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._cooldown = (
            float(cooldown_seconds) if cooldown_seconds is not None else float(self.COOLDOWN_SECONDS)
        )
        self._http_timeout = http_timeout
        # Asset -> zuletzt gesendeter monotonic-Zeitstempel.
        self._last_sent: dict[str, float] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _is_configured(self) -> bool:
        return bool(self._bot_token and self._chat_id)

    def should_send(
        self,
        envelope: CanonicalSignalEnvelope,
        now: float | None = None,
    ) -> tuple[bool, str]:
        """Prüft Priority-Gate und Cooldown ohne Seiteneffekte.

        Liefert ``(send?, grund)``. Der Grund ist ein kurzer Slug
        (z. B. ``"ok"``, ``"priority_low_below_threshold"``,
        ``"cooldown_active"``) und tauglich für Metriken/Logging.
        """
        if envelope.priority not in (SignalPriority.HIGH, SignalPriority.CRITICAL):
            return False, f"priority_{envelope.priority.value}_below_threshold"

        ts = now if now is not None else time.monotonic()
        last = self._last_sent.get(envelope.asset)
        if last is not None and ts - last < self._cooldown:
            return False, "cooldown_active"
        return True, "ok"

    async def send(
        self,
        envelope: CanonicalSignalEnvelope,
        summary: str,
        now: float | None = None,
    ) -> bool:
        """Sendet einen compact Alert, falls Regeln erfüllt und konfiguriert.

        Liefert ``True`` bei erfolgreichem Versand, sonst ``False``
        (nicht konfiguriert, Cooldown aktiv, Priority zu niedrig oder
        HTTP-Fehler).
        """
        if not self._is_configured():
            return False

        ts = now if now is not None else time.monotonic()
        ok, _ = self.should_send(envelope, now=ts)
        if not ok:
            return False

        message = self._format_message(envelope, summary)
        payload: dict[str, Any] = {
            "chat_id": self._chat_id,
            "text": message,
            "parse_mode": "HTML",
        }
        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"

        try:
            async with httpx.AsyncClient(timeout=self._http_timeout) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
        except httpx.HTTPError:
            return False

        self._last_sent[envelope.asset] = ts
        return True

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _format_message(envelope: CanonicalSignalEnvelope, summary: str) -> str:
        """Baue die HTML-Nachricht für Telegram (compact, advisory-only)."""
        emoji = _PRIORITY_EMOJI.get(envelope.priority, "ℹ️")
        pri = envelope.priority.value.upper()
        cls = envelope.signal_class.value.upper()
        direction = envelope.direction.value.upper()

        lines = [
            f"{emoji} <b>[{pri}]</b> Signal Alert",
            f"<b>Asset:</b> <code>{escape(envelope.asset)}</code>",
            f"<b>Class:</b> {cls} · <b>Direction:</b> {direction}",
            f"<b>Confidence:</b> {envelope.confidence:.2f} · <b>Risk:</b> {envelope.risk_score:.2f}",
            f"<b>Summary:</b> {escape(summary)}",
            "<i>advisory only · dry-run</i>",
        ]
        return "\n".join(lines)


async def send_drift_alert(
    win_rate: float,
    baseline: float,
    sample_size: int,
    telegram_token: str,
    chat_id: str,
) -> None:
    """Send a Telegram drift alert using the Telegram Bot API."""
    if not telegram_token or not chat_id:
        return
    msg = (
        "⚠️ *Model Drift Alarm — ai4trade Rainbow*\n\n"
        f"Win-Rate (letzte {sample_size}): `{win_rate:.1%}`\n"
        f"Baseline: `{baseline:.1%}`\n"
        "CUSUM-Threshold überschritten\n\n"
        "→ LLM-Evaluierung und Critic-Review empfohlen"
    )
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"https://api.telegram.org/bot{telegram_token}/sendMessage",
            json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"},
        )
        response.raise_for_status()
