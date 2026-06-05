import asyncio
import logging
import time

import httpx
import pandas as pd

from rainbow.exceptions import ProviderError
from rainbow.market_data.providers import MarketDataProvider

log = logging.getLogger(__name__)

_BITGET_OK_CODE = "00000"


class _TokenBucket:
    """Einfacher Token-Bucket Rate Limiter."""

    def __init__(self, rate: float, burst: int = 1) -> None:
        self._rate = rate
        self._burst = burst
        self._tokens = float(burst)
        self._last = time.monotonic()

    async def acquire(self) -> None:
        while True:
            now = time.monotonic()
            self._tokens = min(self._burst, self._tokens + (now - self._last) * self._rate)
            self._last = now
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return
            await asyncio.sleep((1.0 - self._tokens) / self._rate)


class BitgetClient(MarketDataProvider):
    """Async BitGet REST Client fuer OHLCV- und Preisdaten."""

    def __init__(
        self,
        base_url: str = "https://api.bitget.com",
        rate_limit: float | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout)
        self._limiter = _TokenBucket(rate_limit, burst=3) if rate_limit else None

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "BitgetClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    async def get_ohlcv(self, symbol: str, interval: str = "1h", limit: int = 200) -> pd.DataFrame:
        symbol = _normalize_symbol(symbol)
        body = await self._request(
            "/api/v2/spot/market/candles",
            params={"symbol": symbol, "granularity": interval, "limit": str(limit)},
        )
        return _parse_ohlcv(body["data"])

    async def get_price(self, symbol: str) -> float:
        symbol = _normalize_symbol(symbol)
        body = await self._request(
            "/api/v2/spot/market/tickers",
            params={"symbol": symbol},
        )
        data = body["data"]
        if not data:
            raise ProviderError("bitget", f"Keine Ticker-Daten fuer {symbol}")
        return float(data[0]["lastPr"])

    async def health_check(self) -> bool:
        try:
            await self.get_price("BTCUSDT")
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
    ) -> dict:
        url = f"{self._base_url}{path}"
        last_exc: BaseException | None = None

        for attempt in range(max_retries):
            if self._limiter:
                await self._limiter.acquire()
            try:
                resp = await self._client.get(url, params=params)
            except httpx.TimeoutException as exc:
                last_exc = exc
                log.warning("Bitget Timeout (Versuch %d/%d): %s", attempt + 1, max_retries, exc)
            except httpx.RequestError as exc:
                last_exc = exc
                log.warning("Bitget Netzwerkfehler (Versuch %d/%d): %s", attempt + 1, max_retries, exc)

            else:
                if resp.status_code >= 400:
                    raise ProviderError("bitget", f"HTTP {resp.status_code}: {resp.text[:200]}")

                body = resp.json()
                if body.get("code") != _BITGET_OK_CODE:
                    raise ProviderError("bitget", f"API Fehler: {body.get('msg', 'unknown')}")

                return body

            if attempt < max_retries - 1:
                await asyncio.sleep(backoff_base * (2 ** attempt))

        raise ProviderError("bitget", f"Nach {max_retries} Versuchen gescheitert: {last_exc}")


def _normalize_symbol(symbol: str) -> str:
    return symbol.replace("/", "")


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


def _parse_ohlcv(raw: list[list]) -> pd.DataFrame:
    rows = [
        {
            "timestamp": _normalize_timestamp(candle[0]),
            "open": float(candle[1]),
            "high": float(candle[2]),
            "low": float(candle[3]),
            "close": float(candle[4]),
            "volume": float(candle[5]),
        }
        for candle in raw
    ]
    return pd.DataFrame(rows)
