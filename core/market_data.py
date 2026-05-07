import logging
import time

import pandas as pd
import requests

import config

log = logging.getLogger(__name__)


class MarketData:
    def __init__(self):
        self._session = requests.Session()
        self._binance = config.BINANCE_BASE
        self._coingecko = config.COINGECKO_BASE

    def _retry(self, url, params=None, max_retries=3, backoff_base=1.0, source="binance"):
        last_err = None
        for attempt in range(max_retries):
            try:
                resp = self._session.get(url, params=params, timeout=10)
                resp.raise_for_status()
                return resp
            except requests.RequestException as e:
                last_err = e
                log.warning(f"{source} API Fehler (Versuch {attempt + 1}/{max_retries}): {e}")
                time.sleep(backoff_base * (2 ** attempt))
        raise last_err

    def get_ohlcv(self, symbol: str, interval: str = "1h", limit: int = 200) -> pd.DataFrame:
        try:
            resp = self._retry(
                f"{self._binance}/api/v3/klines",
                params={"symbol": symbol, "interval": interval, "limit": limit},
            )
            return self._parse_binance_ohlcv(resp.json())
        except Exception:
            log.warning(f"Binance fehlgeschlagen, Fallback auf CoinGecko für {symbol}")
            return self._coingecko_ohlcv(symbol, limit)

    def get_price(self, symbol: str) -> float:
        resp = self._retry(
            f"{self._binance}/api/v3/ticker/price",
            params={"symbol": symbol},
        )
        return float(resp.json()["price"])

    def _parse_binance_ohlcv(self, raw: list) -> pd.DataFrame:
        rows = []
        for k in raw:
            rows.append({
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
            })
        return pd.DataFrame(rows)

    def _coingecko_ohlcv(self, symbol: str, limit: int) -> pd.DataFrame:
        coin_id = symbol.lower().replace("usdt", "")
        resp = self._retry(
            f"{self._coingecko}/coins/{coin_id}/ohlc",
            params={"vs_currency": "usd", "days": str(limit // 24 + 1)},
            max_retries=2,
            source="coingecko",
        )
        rows = [
            {"open": p[1], "high": p[2], "low": p[3], "close": p[4], "volume": 0}
            for p in resp.json()
        ]
        return pd.DataFrame(rows)
