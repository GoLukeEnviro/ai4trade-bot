"""Tests for rainbow.collectors.ta_collector — TACollector."""


import numpy as np
import pandas as pd
import pytest

from rainbow.collectors.ta_collector import TACollector
from rainbow.exceptions import CollectorError
from rainbow.models.signal import Direction, SignalType


def _make_ohlcv(n: int = 200, trend: str = "up") -> pd.DataFrame:
    """Generate synthetic OHLCV data with enough rows for TA calculations."""
    np.random.seed(42)
    if trend == "up":
        close = 100.0 + np.cumsum(np.random.randn(n) * 0.5 + 0.1)
    elif trend == "down":
        close = 100.0 - np.cumsum(np.random.randn(n) * 0.5 + 0.1)
    else:
        close = 100.0 + np.random.randn(n) * 2.0

    return pd.DataFrame({
        "open": close - np.random.rand(n) * 0.5,
        "high": close + np.abs(np.random.randn(n)) * 0.3,
        "low": close - np.abs(np.random.randn(n)) * 0.3,
        "close": close,
        "volume": np.random.rand(n) * 1000,
    })


class StubProvider:
    """A stub MarketDataProvider that returns synthetic OHLCV data."""

    def __init__(self, n: int = 200, trend: str = "up"):
        self._df = _make_ohlcv(n, trend)

    async def get_ohlcv(self, asset: str, timeframe: str, limit: int = 200) -> pd.DataFrame:
        return self._df


class TestTACollectorConstruction:
    def test_default_construction(self) -> None:
        provider = StubProvider()
        collector = TACollector(provider=provider, assets=["BTC"])
        assert collector.name == "ta"
        assert collector._assets == ["BTC"]
        assert collector._timeframes == ["1h"]

    def test_custom_construction(self) -> None:
        provider = StubProvider()
        collector = TACollector(
            provider=provider,
            assets=["BTC", "ETH"],
            timeframes=["4h", "1d"],
        )
        assert collector._assets == ["BTC", "ETH"]
        assert collector._timeframes == ["4h", "1d"]


class TestTACollectorCollect:
    async def test_collect_returns_signals(self) -> None:
        provider = StubProvider(n=200)
        collector = TACollector(provider=provider, assets=["BTC"])
        signals = await collector.collect()
        assert len(signals) >= 1
        assert signals[0].signal_type == SignalType.TECHNICAL
        assert signals[0].asset == "BTC"

    async def test_collect_multiple_assets(self) -> None:
        provider = StubProvider(n=200)
        collector = TACollector(provider=provider, assets=["BTC", "ETH"])
        signals = await collector.collect()
        assert len(signals) == 2

    async def test_collect_insufficient_data_raises(self) -> None:
        provider = StubProvider(n=30)  # Less than _MIN_CANDLES=50
        collector = TACollector(provider=provider, assets=["BTC"])
        with pytest.raises(CollectorError, match="Kerzen erforderlich"):
            await collector.collect()


class TestTACollectorScoring:
    def test_direction_label_buy(self) -> None:
        assert TACollector._direction_label(70.0) == "BUY"

    def test_direction_label_sell(self) -> None:
        assert TACollector._direction_label(30.0) == "SELL"

    def test_direction_label_hold(self) -> None:
        assert TACollector._direction_label(50.0) == "HOLD"

    def test_map_direction(self) -> None:
        assert TACollector._map_direction("BUY") == Direction.BULLISH
        assert TACollector._map_direction("SELL") == Direction.BEARISH
        assert TACollector._map_direction("HOLD") == Direction.NEUTRAL

    def test_compute_indicators(self) -> None:
        provider = StubProvider(n=200)
        collector = TACollector(provider=provider, assets=["BTC"])
        df = _make_ohlcv(200)
        result = collector._compute_indicators(df)
        assert "rsi" in result
        assert "macd" in result
        assert "ema_50" in result
        assert "price" in result
        assert 0 <= result["rsi"] <= 100

    def test_score_indicators_clamp(self) -> None:
        provider = StubProvider(n=200)
        collector = TACollector(provider=provider, assets=["BTC"])
        result = collector._score_indicators({
            "rsi": 10, "macd": 5, "macd_hist": 3,
            "ema_50": 100, "ema_200": 90, "price": 200,
            "bb_upper": 250, "bb_lower": 50,
        })
        assert 0.0 <= result <= 100.0
