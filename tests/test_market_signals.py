import time

import pandas as pd

from core.market_signals import MarketSignalAnalyzer
from tests.fixtures.ohlcv_fixtures import make_ohlcv


def _make_stable_trend_ohlcv(n: int = 80) -> pd.DataFrame:
    rows = []
    price = 50000.0
    for _ in range(n):
        change = 0.002
        open_ = price
        close = price * (1 + change)
        high = max(open_, close) * 1.005
        low = min(open_, close) * 0.995
        volume = 500
        rows.append([open_, high, low, close, volume])
        price = close
    return pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"])


def _make_choppy_ohlcv(n: int = 80) -> pd.DataFrame:
    rows = []
    price = 50000.0
    for i in range(n):
        change = 0.03 if i % 2 == 0 else -0.03
        open_ = price
        close = price * (1 + change)
        high = max(open_, close) * 1.02
        low = min(open_, close) * 0.98
        volume = 500 + (i % 5) * 20
        rows.append([open_, high, low, close, volume])
        price = close
    return pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"])


def test_volume_spike_and_breakout_watch():
    df = _make_stable_trend_ohlcv()
    df.loc[df.index[-1], "volume"] = df["volume"].iloc[-20:-1].mean() * 3

    result = MarketSignalAnalyzer().analyze(df)

    assert result["volume"]["spike"] is True
    assert result["market_state"] == "breakout_watch"
    assert result["confidence_adjustment"] > 0


def test_volume_dry_up_and_thin_market_stress():
    df = _make_choppy_ohlcv()
    df.loc[df.index[-1], "volume"] = 1

    result = MarketSignalAnalyzer().analyze(df)

    assert result["volume"]["dry_up"] is True
    assert result["risk_off"] is True
    assert result["no_trade_reason"] == "thin_market_stress"


def test_feed_health_marks_stale_data_unhealthy():
    df = make_ohlcv(60, 50000, "up")
    now = time.time()
    df["timestamp"] = [now - (5 * 3600) + i * 60 for i in range(len(df))]

    result = MarketSignalAnalyzer().analyze(df, expected_interval_seconds=3600)

    assert result["feed_health"]["timestamp_available"] is True
    assert result["feed_health"]["is_healthy"] is False
    assert result["risk_off"] is True
