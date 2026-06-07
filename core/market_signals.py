from __future__ import annotations

import time

import pandas as pd


class MarketSignalAnalyzer:
    def analyze(self, df: pd.DataFrame, expected_interval_seconds: int = 3600) -> dict:
        if len(df) < 50:
            raise ValueError("mindestens 50 Kerzen benötigt")

        volume = self._volume_features(df["volume"])
        volatility = self._volatility_features(df["close"])
        feed_health = self._feed_health(df, expected_interval_seconds)
        risk_off = self._risk_off(volume, volatility, feed_health)
        confidence_adjustment = self._confidence_adjustment(volume, volatility, risk_off)

        return {
            "market_state": self._market_state(volume, volatility, risk_off),
            "risk_off": risk_off,
            "confidence_adjustment": confidence_adjustment,
            "no_trade_reason": self._no_trade_reason(volume, volatility, feed_health, risk_off),
            "volume": volume,
            "volatility": volatility,
            "feed_health": feed_health,
        }

    def _volume_features(self, volume: pd.Series) -> dict:
        window = min(20, len(volume))
        rolling = volume.rolling(window=window, min_periods=window)
        current = float(volume.iloc[-1])
        average = float(rolling.mean().iloc[-1])
        median = float(rolling.median().iloc[-1])
        ratio = current / average if average > 0 else 1.0

        return {
            "current": round(current, 2),
            "average": round(average, 2),
            "median": round(median, 2),
            "ratio": round(ratio, 2),
            "spike": ratio >= 1.5,
            "dry_up": ratio <= 0.3,
        }

    def _volatility_features(self, close: pd.Series) -> dict:
        returns = close.pct_change().dropna()
        short_window = min(20, len(returns))
        long_window = min(50, len(returns))
        short_vol = float(returns.rolling(window=short_window, min_periods=short_window).std().iloc[-1])
        long_vol = float(returns.rolling(window=long_window, min_periods=long_window).std().iloc[-1])
        ratio = short_vol / long_vol if long_vol > 0 else 1.0

        return {
            "short": round(short_vol, 4),
            "long": round(long_vol, 4),
            "ratio": round(ratio, 2),
            "high": short_vol > 0 and ratio >= 1.25,
            "extreme": short_vol > 0 and ratio >= 1.75,
        }

    def _feed_health(self, df: pd.DataFrame, expected_interval_seconds: int) -> dict:
        timestamp = self._latest_timestamp(df)
        zero_volume_share = float((pd.to_numeric(df["volume"], errors="coerce").fillna(0) == 0).mean())
        healthy_volume = zero_volume_share < 0.8

        if timestamp is None:
            return {
                "is_healthy": healthy_volume,
                "timestamp_available": False,
                "staleness_seconds": None,
                "threshold_seconds": expected_interval_seconds * 3,
                "zero_volume_share": round(zero_volume_share, 2),
                "source_quality": "degraded" if not healthy_volume else "normal",
            }

        age_seconds = max(0.0, time.time() - timestamp)
        threshold_seconds = float(expected_interval_seconds * 3)
        stale = age_seconds > threshold_seconds

        return {
            "is_healthy": healthy_volume and not stale,
            "timestamp_available": True,
            "staleness_seconds": round(age_seconds, 1),
            "threshold_seconds": threshold_seconds,
            "zero_volume_share": round(zero_volume_share, 2),
            "source_quality": "degraded" if not healthy_volume else "normal",
        }

    def _latest_timestamp(self, df: pd.DataFrame) -> float | None:
        if "timestamp" in df.columns:
            series = pd.to_numeric(df["timestamp"], errors="coerce").dropna()
            if not series.empty:
                value = float(series.iloc[-1])
                if value <= 0:
                    return None
                if value > 1e11:
                    return value / 1000.0
                return value

        if isinstance(df.index, pd.DatetimeIndex) and len(df.index) > 0:
            return float(df.index[-1].timestamp())

        return None

    def _risk_off(self, volume: dict, volatility: dict, feed_health: dict) -> bool:
        if not feed_health["is_healthy"]:
            return True
        return volume["dry_up"] or volatility["extreme"]

    def _confidence_adjustment(self, volume: dict, volatility: dict, risk_off: bool) -> int:
        if risk_off:
            return 0

        adjustment = 0
        if volume["spike"]:
            adjustment += 6
        if volume["dry_up"]:
            adjustment -= 15
        if volatility["high"]:
            adjustment -= 10
        return adjustment

    def _market_state(self, volume: dict, volatility: dict, risk_off: bool) -> str:
        if risk_off:
            return "risk_off"
        if volume["spike"] and not volatility["high"]:
            return "breakout_watch"
        if volume["dry_up"]:
            return "quiet"
        if volatility["high"]:
            return "volatile"
        return "normal"

    def _no_trade_reason(self, volume: dict, volatility: dict, feed_health: dict, risk_off: bool) -> str:
        if not feed_health["is_healthy"]:
            return "feed_unhealthy"
        if volume["dry_up"]:
            return "thin_market_stress"
        if risk_off and volatility["extreme"]:
            return "extreme_volatility"
        return ""
