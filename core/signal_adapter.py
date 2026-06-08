# core/signal_adapter.py
"""Canonical Signal Layer — converts between legacy Signal and Rainbow CryptoSignal formats."""

from __future__ import annotations

import time

from core.signal_model import Signal

# Direction mapping: legacy action -> Rainbow direction
_ACTION_TO_DIRECTION = {
    "BUY": "bullish",
    "SELL": "bearish",
    "HOLD": "neutral",
}

_DIRECTION_TO_ACTION: dict[str, str] = {v: k for k, v in _ACTION_TO_DIRECTION.items()}
# Override: neutral -> HOLD
_DIRECTION_TO_ACTION["neutral"] = "HOLD"


class SignalAdapter:
    """Bidirectional converter between legacy Signal and Rainbow CryptoSignal dicts."""

    @staticmethod
    def legacy_signal_to_rainbow(signal: Signal) -> dict:
        """Convert a legacy Signal dataclass to a dict compatible with CryptoSignal fields.

        Field mappings:
            pair      -> asset (slashes removed)
            action    -> direction (BUY->bullish, SELL->bearish, HOLD->neutral)
            confidence (0-100) -> confidence (0.0-1.0) and strength (0.0-1.0)
            price     -> value
            timestamp -> timestamp (ISO-8601)
        """
        return {
            "source": "legacy_strategy",
            "asset": signal.pair.replace("/", ""),
            "signal_type": "technical",
            "direction": _ACTION_TO_DIRECTION.get(signal.action, "neutral"),
            "strength": min(signal.confidence / 100.0, 1.0),
            "confidence": min(signal.confidence / 100.0, 1.0),
            "value": signal.price,
            "raw_data": signal.to_dict(),
            "metadata": {
                "pair": signal.pair,
                "action": signal.action,
                "quantity": signal.quantity,
                "mode": signal.mode,
            },
        }

    @staticmethod
    def rainbow_dict_to_signal(data: dict) -> Signal:
        """Convert a CryptoSignal-compatible dict back to a legacy Signal dataclass.

        Field mappings:
            asset     -> pair (slash re-inserted before /USDT or /BTC)
            direction -> action (bullish->BUY, bearish->SELL, neutral->HOLD)
            confidence (0.0-1.0) -> confidence (0-100)
            value     -> price
            timestamp preserved if present
        """
        # Reconstruct pair from asset
        asset = data.get("asset", "")
        pair = _asset_to_pair(asset)

        # Direction -> action
        direction = data.get("direction", "neutral")
        action = _DIRECTION_TO_ACTION.get(direction, "HOLD")

        # Confidence: 0.0-1.0 -> 0-100
        confidence_float = float(data.get("confidence", 0.0))
        confidence = min(100, max(0, int(confidence_float * 100)))

        price = float(data.get("value", 0.0))
        quantity = 0.0
        timestamp = float(data.get("timestamp", time.time()))

        return Signal(
            pair=pair,
            action=action,
            confidence=confidence,
            price=price,
            quantity=quantity,
            timestamp=timestamp,
        )


def _asset_to_pair(asset: str) -> str:
    """Best-effort conversion of asset symbol back to trading pair format.

    Examples: BTCUSDT -> BTC/USDT, ETHBTC -> ETH/BTC
    """
    known_quotes = ["USDT", "BUSD", "USD", "BTC", "ETH", "EUR"]
    for quote in known_quotes:
        if asset.endswith(quote) and len(asset) > len(quote):
            base = asset[: -len(quote)]
            return f"{base}/{quote}"
    # Fallback: return as-is
    return asset
