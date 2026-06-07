# adapters/rainbow_publisher.py
"""Publishes legacy Signal objects to the Rainbow Engine via REST API."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from core.signal_model import Signal

log = logging.getLogger(__name__)

RAINBOW_API_URL = os.getenv("RAINBOW_API_URL", "http://localhost:8000")


class RainbowApiPublisher:
    """POST legacy signals to Rainbow Engine /signals/ingest endpoint."""

    def __init__(self, base_url: str | None = None, timeout: float = 3.0) -> None:
        self._base_url = (base_url or RAINBOW_API_URL).rstrip("/")
        self._timeout = timeout

    def publish(self, signal: Signal) -> bool:
        """Convert legacy Signal → CryptoSignal dict and POST to Rainbow.

        Returns True on success, False on any failure (graceful).
        """
        direction = self._map_action(signal.action)
        payload = {
            "asset": signal.pair.replace("/", ""),
            "source": "legacy_strategy",
            "signal_type": "technical",
            "direction": direction,
            "strength": min(signal.confidence / 100.0, 1.0),
            "confidence": min(signal.confidence / 100.0, 1.0),
            "value": signal.price,
            "raw_data": signal.to_dict(),
            "metadata": {
                "pair": signal.pair,
                "confidence_raw": signal.confidence,
                "mode": signal.mode,
            },
        }

        try:
            resp = requests.post(
                f"{self._base_url}/signals/ingest",
                json=payload,
                timeout=self._timeout,
            )
            if resp.status_code == 200:
                log.info(
                    "Rainbow publish OK: %s %s → %s",
                    signal.pair,
                    signal.action,
                    resp.json().get("signal_id", "?"),
                )
                return True
            log.warning(
                "Rainbow publish failed (%d): %s",
                resp.status_code,
                resp.text[:200],
            )
            return False
        except requests.RequestException as exc:
            log.warning("Rainbow publish error: %s", exc)
            return False

    @staticmethod
    def _map_action(action: str) -> str:
        """Map legacy BUY/SELL/HOLD → Rainbow direction enum."""
        mapping = {"BUY": "bullish", "SELL": "bearish", "HOLD": "neutral"}
        return mapping.get(action, "neutral")
