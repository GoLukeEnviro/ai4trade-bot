"""Pure eligibility policy for legacy-compatible technical signal transport."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from rainbow.delivery.models import AI4TradePayload, DeliveryConfig, EligibilityResult


class DeliveryPolicy:
    """Convert only fresh, priced technical signals into AI4Trade payloads."""

    def __init__(self, config: DeliveryConfig) -> None:
        self._config = config

    def evaluate(self, raw_signal: dict[str, object], *, now: datetime) -> EligibilityResult:
        signal_type = raw_signal.get("signal_type")
        if signal_type != "technical":
            return EligibilityResult(payload=None, reason="non_technical_signal")

        signal_id = raw_signal.get("signal_id")
        asset = raw_signal.get("asset")
        if not isinstance(signal_id, str) or not signal_id or not isinstance(asset, str):
            return EligibilityResult(payload=None, reason="invalid_signal_identity")

        route = self._config.asset_routes.get(asset.upper())
        if route is None or route.quantity <= 0 or not route.ai4trade_symbol:
            return EligibilityResult(payload=None, reason="asset_not_authorized")

        timestamp = self._parse_timestamp(raw_signal.get("timestamp"))
        if timestamp is None or (now - timestamp).total_seconds() > self._config.max_signal_age_seconds:
            return EligibilityResult(payload=None, reason="stale_signal")

        action = self._action(raw_signal)
        if action is None:
            return EligibilityResult(payload=None, reason="hold_signal")

        price = raw_signal.get("value")
        if not isinstance(price, (int, float)) or isinstance(price, bool) or price <= 0:
            return EligibilityResult(payload=None, reason="invalid_technical_price")

        fingerprint_source = json.dumps(
            [signal_id, action, route.ai4trade_symbol, float(price), route.quantity],
            separators=(",", ":"),
        )
        fingerprint = hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest()
        return EligibilityResult(
            payload=AI4TradePayload(
                fingerprint=fingerprint,
                signal_id=signal_id,
                market="crypto",
                action=action,
                symbol=route.ai4trade_symbol,
                price=float(price),
                quantity=route.quantity,
            )
        )

    @staticmethod
    def _action(raw_signal: dict[str, object]) -> str | None:
        direction = raw_signal.get("direction")
        strength = raw_signal.get("strength")
        if not isinstance(strength, (int, float)) or isinstance(strength, bool):
            return None
        if direction == "bullish" and strength > 0.65:
            return "BUY"
        if direction == "bearish" and strength < 0.35:
            return "SELL"
        return None

    @staticmethod
    def _parse_timestamp(value: object) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
