from __future__ import annotations

import logging

import httpx
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

FEAR_GREED_API_URL = "https://api.alternative.me/fng/?limit=1"


class FeaturePipeline:
    """Transforms OHLCV + external data into ML-ready features."""

    def build_features(self, ohlcv: pd.DataFrame) -> pd.DataFrame:
        if ohlcv.empty:
            return pd.DataFrame()

        df = ohlcv.copy()

        df["returns_1h"] = df["close"].pct_change(1, fill_method=None)
        df["returns_4h"] = df["close"].pct_change(4, fill_method=None) if len(df) >= 4 else np.nan
        df["returns_24h"] = df["close"].pct_change(24, fill_method=None) if len(df) >= 24 else np.nan

        df["log_returns"] = np.log1p(df["close"].pct_change(fill_method=None))

        df["volatility_20"] = df["log_returns"].rolling(20).std()
        df["volatility_50"] = df["log_returns"].rolling(50).std()

        delta = df["close"].diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, 1e-10)
        df["rsi_14"] = 100 - (100 / (1 + rs))

        if "hour" not in df.columns:
            if isinstance(df.index, pd.DatetimeIndex):
                hour = df.index.hour
            elif "timestamp" in df.columns:
                hour = pd.to_datetime(df["timestamp"]).dt.hour
            else:
                hour = 0
        else:
            hour = df["hour"]

        df["hour_sin"] = np.sin(2 * np.pi * hour / 24)
        df["hour_cos"] = np.cos(2 * np.pi * hour / 24)

        if isinstance(df.index, pd.DatetimeIndex):
            dow = df.index.dayofweek
        elif "timestamp" in df.columns:
            dow = pd.to_datetime(df["timestamp"]).dt.dayofweek
        else:
            dow = 0

        df["day_of_week_sin"] = np.sin(2 * np.pi * dow / 7)
        df["day_of_week_cos"] = np.cos(2 * np.pi * dow / 7)

        typical_price = (df["high"] + df["low"] + df["close"]) / 3
        volume = df["volume"] if "volume" in df.columns else 1
        cum_vol = volume.cumsum().replace(0, 1)
        cum_tp_vol = (typical_price * volume).cumsum()
        df["vwap"] = cum_tp_vol / cum_vol

        return df

    async def add_fear_greed(self, features: pd.DataFrame) -> pd.DataFrame:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(FEAR_GREED_API_URL)
                resp.raise_for_status()
                data = resp.json()
                fg_value = int(data["data"][0]["value"])
                fg_class = data["data"][0]["value_classification"]
        except Exception as exc:
            logger.warning("Fear & Greed fetch failed: %s", exc)
            fg_value = None
            fg_class = None

        features["fear_greed_value"] = fg_value
        features["fear_greed_class"] = fg_class
        return features
