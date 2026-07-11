"""Configuration and value objects for isolated signal delivery."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from enum import Enum


class DeliveryMode(str, Enum):
    OFF = "off"
    SHADOW = "shadow"
    LIVE = "live"


@dataclass(frozen=True)
class AssetRoute:
    ai4trade_symbol: str
    quantity: float


@dataclass(frozen=True)
class AI4TradePayload:
    fingerprint: str
    signal_id: str
    market: str
    action: str
    symbol: str
    price: float
    quantity: float

    def as_request_json(self) -> dict[str, object]:
        return {
            "market": self.market,
            "action": self.action,
            "symbol": self.symbol,
            "price": self.price,
            "quantity": self.quantity,
        }


@dataclass
class DeliveryConfig:
    mode: DeliveryMode = DeliveryMode.OFF
    provider_base_url: str = "http://127.0.0.1:8000"
    ai4trade_base_url: str = "https://ai4trade.ai/api"
    token: str = ""
    asset_routes: dict[str, AssetRoute] = field(default_factory=dict)
    outbox_path: str = "storage/ai4trade_delivery.db"
    max_signal_age_seconds: int = 900
    max_attempts: int = 3
    heartbeat_enabled: bool = False

    @classmethod
    def from_environment(cls) -> "DeliveryConfig":
        raw_routes = os.getenv("AI4TRADE_DELIVERY_ASSET_ROUTES", "{}")
        parsed_routes = json.loads(raw_routes)
        if not isinstance(parsed_routes, dict):
            raise ValueError("AI4TRADE_DELIVERY_ASSET_ROUTES must be a JSON object")

        routes: dict[str, AssetRoute] = {}
        for asset, route in parsed_routes.items():
            if not isinstance(asset, str) or not isinstance(route, dict):
                raise ValueError("Asset routes must map strings to objects")
            symbol = route.get("symbol")
            quantity = route.get("quantity")
            if not isinstance(symbol, str) or not isinstance(quantity, (int, float)):
                raise ValueError(f"Invalid route for asset {asset!r}")
            routes[asset.upper()] = AssetRoute(symbol, float(quantity))

        return cls(
            mode=DeliveryMode(os.getenv("AI4TRADE_DELIVERY_MODE", DeliveryMode.OFF.value).lower()),
            provider_base_url=os.getenv("AI4TRADE_DELIVERY_PROVIDER_URL", "http://127.0.0.1:8000"),
            ai4trade_base_url=os.getenv("AI4TRADE_BASE_URL", "https://ai4trade.ai/api"),
            token=os.getenv("AI4TRADE_TOKEN", ""),
            asset_routes=routes,
            outbox_path=os.getenv("AI4TRADE_DELIVERY_OUTBOX_PATH", "storage/ai4trade_delivery.db"),
            max_signal_age_seconds=int(os.getenv("AI4TRADE_DELIVERY_MAX_AGE_SECONDS", "900")),
            max_attempts=int(os.getenv("AI4TRADE_DELIVERY_MAX_ATTEMPTS", "3")),
            heartbeat_enabled=os.getenv("AI4TRADE_DELIVERY_HEARTBEAT_ENABLED", "false").lower() == "true",
        )


@dataclass(frozen=True)
class EligibilityResult:
    payload: AI4TradePayload | None
    reason: str | None = None


@dataclass(frozen=True)
class DeliveryRunResult:
    mode: DeliveryMode
    skipped: int = 0
    shadowed: int = 0
    sent: int = 0
    retried: int = 0
    dead_lettered: int = 0
    auth_failed: bool = False
