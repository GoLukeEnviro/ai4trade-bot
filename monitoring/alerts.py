"""Monitoring alert helpers."""

from __future__ import annotations

import httpx


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
