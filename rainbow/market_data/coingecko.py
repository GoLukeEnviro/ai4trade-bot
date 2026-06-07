import asyncio
import logging

import httpx
import pandas as pd

from rainbow.exceptions import ProviderError
from rainbow.market_data.providers import MarketDataProvider

log = logging.getLogger(__name__)


class CoinGeckoClient(MarketDataProvider):
    """Async CoinGecko Client als Fallback-Marktdaten-Provider."""

    def __init__(
        self,
        base_url: str = "https://api.coingecko.com/api/v3",
        timeout: float = 10.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "CoinGeckoClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    async def get_ohlcv(self, symbol: str, interval: str = "1h", limit: int = 200) -> pd.DataFrame:
        coin_id = _symbol_to_coin_id(symbol)
        days = max(1, limit // 24 + 1)

        body = await self._request(
            f"/coins/{coin_id}/ohlc",
            params={"vs_currency": "usd", "days": str(days)},
        )

        rows = [
            {
                "timestamp": _normalize_timestamp(point[0]),
                "open": point[1],
                "high": point[2],
                "low": point[3],
                "close": point[4],
                "volume": 0,
            }
            for point in body
        ]
        return pd.DataFrame(rows)

    async def get_price(self, symbol: str) -> float:
        coin_id = _symbol_to_coin_id(symbol)
        body = await self._request(
            "/simple/price",
            params={"ids": coin_id, "vs_currencies": "usd"},
        )
        if coin_id not in body:
            raise ProviderError("coingecko", f"Keine Preisdaten fuer {coin_id}")
        return float(body[coin_id]["usd"])

    async def health_check(self) -> bool:
        try:
            await self._request("/ping")
            return True
        except ProviderError:
            return False

    async def _request(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
        max_retries: int = 3,
        backoff_base: float = 1.0,
    ) -> dict | list:
        url = f"{self._base_url}{path}"
        last_exc: BaseException | None = None

        for attempt in range(max_retries):
            try:
                resp = await self._client.get(url, params=params)
            except httpx.TimeoutException as exc:
                last_exc = exc
                log.warning("CoinGecko Timeout (Versuch %d/%d): %s", attempt + 1, max_retries, exc)
            except httpx.RequestError as exc:
                last_exc = exc
                log.warning("CoinGecko Netzwerkfehler (Versuch %d/%d): %s", attempt + 1, max_retries, exc)

            else:
                if resp.status_code == 429:
                    last_exc = ProviderError("coingecko", "Rate limit erreicht (429)")
                    log.warning("CoinGecko Rate Limit (Versuch %d/%d)", attempt + 1, max_retries)
                elif resp.status_code >= 400:
                    raise ProviderError("coingecko", f"HTTP {resp.status_code}: {resp.text[:200]}")
                else:
                    return resp.json()

            if attempt < max_retries - 1:
                await asyncio.sleep(backoff_base * (2 ** attempt))

        raise ProviderError("coingecko", f"Nach {max_retries} Versuchen gescheitert: {last_exc}")


def _symbol_to_coin_id(symbol: str) -> str:
    return symbol.lower().replace("usdt", "").replace("/", "")


def _normalize_timestamp(value: object) -> float | None:
    try:
        timestamp = float(value)
    except (TypeError, ValueError):
        return None

    if timestamp <= 0:
        return None
    if timestamp > 1e11:
        return timestamp / 1000.0
    if timestamp > 1e9:
        return timestamp
    return None
