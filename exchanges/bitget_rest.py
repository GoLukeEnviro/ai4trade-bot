from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import pandas as pd
import requests

import config

if TYPE_CHECKING:
    from adapters.rate_limiter import TokenBucketRateLimiter
    from core.ssl_context import CertificatePinning

log = logging.getLogger(__name__)


class BitgetRestClient:
    def __init__(
        self, rate_limiter: "TokenBucketRateLimiter | None" = None, cert_pinning: "CertificatePinning | None" = None
    ):
        self._session = requests.Session()
        self._base = config.BITGET_BASE
        self._rate_limiter = rate_limiter
        self._cert_pinning = cert_pinning

    def get_ohlcv(self, symbol: str, interval: str = "1h", limit: int = 200) -> pd.DataFrame:
        symbol = self._normalize_symbol(symbol)
        resp = self._retry(
            f"{self._base}/api/v2/spot/market/candles",
            params={"symbol": symbol, "granularity": interval, "limit": str(limit)},
        )
        return self._parse_ohlcv(resp.json()["data"])

    def get_price(self, symbol: str) -> float:
        symbol = self._normalize_symbol(symbol)
        resp = self._retry(
            f"{self._base}/api/v2/spot/market/tickers",
            params={"symbol": symbol},
        )
        data = resp.json()["data"]
        if not data:
            raise ValueError(f"Keine Ticker-Daten fuer {symbol}")
        return float(data[0]["lastPr"])

    def _retry(self, url, params=None, max_retries=3, backoff_base=1.0):
        last_err = None
        for attempt in range(max_retries):
            try:
                if self._rate_limiter:
                    self._rate_limiter.acquire()
                resp = self._session.get(url, params=params, timeout=10)
                resp.raise_for_status()
                body = resp.json()
                if body.get("code") != "00000":
                    raise requests.RequestException(f"Bitget API Fehler: {body.get('msg', 'unknown')}")
                return resp
            except requests.RequestException as e:
                last_err = e
                log.warning(f"Bitget API Fehler (Versuch {attempt + 1}/{max_retries}): {e}")
                time.sleep(backoff_base * (2**attempt))
        raise last_err

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        return symbol.replace("/", "")

    @staticmethod
    def _parse_ohlcv(raw: list) -> pd.DataFrame:
        rows = []
        for candle in raw:
            rows.append(
                {
                    "timestamp": BitgetRestClient._parse_timestamp(candle[0]),
                    "open": float(candle[1]),
                    "high": float(candle[2]),
                    "low": float(candle[3]),
                    "close": float(candle[4]),
                    "volume": float(candle[5]),
                }
            )
        return pd.DataFrame(rows)

    @staticmethod
    def _parse_timestamp(value) -> float | None:
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
