"""Binance USD-M futures derivatives collector."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from rainbow.collectors.base import BaseCollector
from rainbow.models.signal import CryptoSignal, Direction, SignalType

FUNDING_EXTREME_POSITIVE = 0.0005
FUNDING_EXTREME_NEGATIVE = -0.0003
OI_SPIKE_MULTIPLIER = 1.5


class DerivativesCollector(BaseCollector):
    """Collect funding-rate and open-interest risk signals from Binance Futures."""

    def __init__(
        self,
        assets: list[str],
        base_url: str = "https://fapi.binance.com",
        funding_extreme_threshold: float = FUNDING_EXTREME_POSITIVE,
        oi_spike_multiplier: float = OI_SPIKE_MULTIPLIER,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._assets = assets
        self._base_url = base_url.rstrip("/")
        self._funding_extreme_threshold = funding_extreme_threshold
        self._oi_spike_multiplier = oi_spike_multiplier
        self._client = client
        self.last_run_utc: str | None = None
        self.funding_rate_btc_current: float | None = None

    @property
    def name(self) -> str:
        return "derivatives"

    async def collect(self) -> list[CryptoSignal]:
        signals: list[CryptoSignal] = []
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=10.0)
        try:
            for asset in self._assets:
                symbol = self.map_symbol(asset)
                funding = await self._get_json(client, "/fapi/v1/premiumIndex", {"symbol": symbol})
                oi = await self._get_json(client, "/fapi/v1/openInterest", {"symbol": symbol})
                await self._get_json(
                    client,
                    "/futures/data/globalLongShortAccountRatio",
                    {"symbol": symbol, "period": "5m", "limit": 1},
                )
                rate = float(funding["lastFundingRate"])
                oi_value = float(oi["openInterest"])
                if symbol == "BTCUSDT":
                    self.funding_rate_btc_current = rate
                funding_signal = self._funding_signal(asset, symbol, rate)
                if funding_signal is not None:
                    signals.append(funding_signal)
                oi_avg = await self._get_oi_24h_average(symbol, oi_value)
                if oi_avg > 0 and oi_value > oi_avg * self._oi_spike_multiplier:
                    signals.append(self._oi_signal(asset, symbol, oi_value, oi_avg))
            self.last_run_utc = datetime.now(UTC).isoformat()
            return signals
        finally:
            if owns_client:
                await client.aclose()

    @staticmethod
    def map_symbol(asset: str) -> str:
        return asset.split(":", 1)[0].replace("/", "")

    async def _get_json(self, client: httpx.AsyncClient, path: str, params: dict[str, str | int]) -> dict:
        response = await client.get(f"{self._base_url}{path}", params=params)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list):
            return data[0] if data else {}
        return data

    async def _get_oi_24h_average(self, symbol: str, current_oi: float) -> float:
        return current_oi

    def _funding_signal(self, asset: str, symbol: str, rate: float) -> CryptoSignal | None:
        if rate > self._funding_extreme_threshold:
            subtype = "FUNDING_EXTREME_POSITIVE"
            direction = Direction.BEARISH
            confidence = 0.70
        elif rate < FUNDING_EXTREME_NEGATIVE:
            subtype = "FUNDING_EXTREME_NEGATIVE"
            direction = Direction.BULLISH
            confidence = 0.65
        else:
            return None
        return CryptoSignal(
            source="binance_derivatives",
            asset=asset,
            signal_type=SignalType.MACRO,
            direction=direction,
            strength=round(min(abs(rate) / 0.002, 1.0), 3),
            confidence=confidence,
            value=rate,
            raw_data={"symbol": symbol, "funding_rate": rate},
            metadata={"subtype": subtype, "signal_class": "risk", "can_execute": False, "dry_run_only": True},
        )

    def _oi_signal(self, asset: str, symbol: str, oi_value: float, oi_24h_avg: float) -> CryptoSignal:
        return CryptoSignal(
            source="binance_derivatives",
            asset=asset,
            signal_type=SignalType.MACRO,
            direction=Direction.NEUTRAL,
            strength=round(min((oi_value / oi_24h_avg - 1.0) / 0.5, 1.0), 3),
            confidence=0.60,
            value=oi_value,
            raw_data={"symbol": symbol, "open_interest": oi_value, "open_interest_24h_avg": oi_24h_avg},
            metadata={"subtype": "OI_SPIKE", "signal_class": "risk", "can_execute": False, "dry_run_only": True},
        )
