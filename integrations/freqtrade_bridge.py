# integrations/freqtrade_bridge.py
"""Freqtrade Signal Bridge — polls Rainbow Engine for trading signals.

Freqtrade Custom Strategy can use this bridge to consume signals from
the Rainbow Intelligence Engine via HTTP.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import requests

log = logging.getLogger(__name__)

RAINBOW_API_URL = os.getenv("RAINBOW_API_URL", "http://localhost:8000")


class FreqtradeSignalBridge:
    """HTTP client that polls Rainbow Engine for trading signals.

    Features:
    - Rate limiting: max 1 request/second per pair
    - Timeout: 2s default, graceful fallback to HOLD
    - Caches last signal to avoid redundant API calls
    """

    def __init__(
        self,
        api_url: str | None = None,
        timeout: float = 2.0,
        min_request_interval: float = 1.0,
    ) -> None:
        self._api_url = (api_url or RAINBOW_API_URL).rstrip("/")
        self._timeout = timeout
        self._min_interval = min_request_interval
        self._last_request_time: dict[str, float] = {}
        self._cache: dict[str, dict] = {}

    def get_signal(self, pair: str) -> dict[str, Any]:
        """Get the latest signal for a pair from Rainbow Engine.

        Returns:
            dict with keys: action (BUY|SELL|HOLD), confidence (0-100),
            ai_confidence (0.0-1.0)
            On failure: {action: "HOLD", confidence: 0}
        """
        now = time.monotonic()
        last = self._last_request_time.get(pair, 0.0)

        # Rate limit check
        if now - last < self._min_interval:
            cached = self._cache.get(pair)
            if cached:
                return cached

        try:
            symbol = pair.replace("/", "").replace("_", "")
            resp = requests.get(
                f"{self._api_url}/signals/latest",
                params={"asset": symbol, "limit": 1},
                timeout=self._timeout,
            )

            if resp.status_code != 200:
                log.warning("Rainbow API returned %d for %s", resp.status_code, pair)
                return self._hold()

            data = resp.json()
            if not data or not isinstance(data, list) or len(data) == 0:
                return self._hold()

            signal = data[0]
            direction = signal.get("direction", "neutral")
            action_map = {"bullish": "BUY", "bearish": "SELL"}
            action = action_map.get(direction, "HOLD")

            confidence = int((signal.get("confidence", 0.0) or 0.0) * 100)
            ai_confidence = 0.0
            ai_eval = signal.get("ai_evaluation")
            if ai_eval and isinstance(ai_eval, dict):
                ai_confidence = float(ai_eval.get("ai_confidence", 0.0))

            result = {
                "action": action,
                "confidence": confidence,
                "ai_confidence": ai_confidence,
                "signal_id": signal.get("signal_id", ""),
                "asset": signal.get("asset", ""),
                "source": signal.get("source", ""),
            }

            # Cache and update rate limiter
            self._cache[pair] = result
            self._last_request_time[pair] = now

            return result

        except requests.RequestException as exc:
            log.warning("Rainbow API error for %s: %s", pair, exc)
            return self._hold()

    @staticmethod
    def _hold() -> dict[str, Any]:
        return {"action": "HOLD", "confidence": 0, "ai_confidence": 0.0}
