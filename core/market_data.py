import logging
import time

import pandas as pd
import requests

import config
from exchanges.base import ExchangeClient
from exchanges.factory import create_exchange

log = logging.getLogger(__name__)


class MarketData:
    def __init__(self, exchange: ExchangeClient = None):
        self._exchange = exchange or create_exchange()
        self._session = requests.Session()
        self._coingecko = config.COINGECKO_BASE

    def _retry(self, url, params=None, max_retries=3, backoff_base=1.0, source="coingecko"):
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
            return self._exchange.get_ohlcv(symbol, interval, limit)
        except Exception:
            log.warning(f"Exchange fehlgeschlagen, Fallback auf CoinGecko fuer {symbol}")
            return self._coingecko_ohlcv(symbol, limit)

    def get_price(self, symbol: str) -> float:
        return self._exchange.get_price(symbol)

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
