"""Cross-repository compatibility tests for Rainbow signal output."""

from pathlib import Path

import pytest

from core.signals.adapters import from_rainbow_signal
from rainbow.collectors.ta_collector import TACollector
from rainbow.models.signal import CryptoSignal, Direction, SignalType
from rainbow.symbols import canonical_symbol_for_asset


def test_known_rainbow_asset_maps_to_trading_hub_symbol() -> None:
    assert canonical_symbol_for_asset("BTC") == "BTC/USDT:USDT"


def test_every_known_rainbow_signal_carries_canonical_symbol_metadata() -> None:
    signal = CryptoSignal(
        source="news_btc",
        asset="BTC",
        signal_type=SignalType.NEWS,
        direction=Direction.NEUTRAL,
        strength=0.5,
        confidence=0.5,
    )

    assert signal.metadata["canonical_symbol"] == "BTC/USDT:USDT"


def test_rainbow_adapter_preserves_canonical_symbol_and_timeframe() -> None:
    signal = CryptoSignal(
        source="ta_1h",
        asset="BTC",
        signal_type=SignalType.TECHNICAL,
        direction=Direction.BULLISH,
        strength=0.8,
        confidence=0.8,
        metadata={"canonical_symbol": "BTC/USDT:USDT", "timeframe": "1h"},
    )

    envelope = from_rainbow_signal(signal)

    assert envelope.asset == "BTC/USDT:USDT"
    assert envelope.timeframe == "1h"


class _StaticProvider:
    async def get_ohlcv(self, asset: str, timeframe: str, limit: int = 200):
        return pytest.importorskip("pandas").DataFrame(
            {
                "timestamp": [1_700_000_000.0 + i * 3600 for i in range(200)],
                "open": [50_000.0 + i for i in range(200)],
                "high": [50_100.0 + i for i in range(200)],
                "low": [49_900.0 + i for i in range(200)],
                "close": [50_000.0 + i for i in range(200)],
                "volume": [1_000.0 + i for i in range(200)],
            }
        )


@pytest.mark.anyio
async def test_ta_collector_emits_canonical_symbol_metadata() -> None:
    collector = TACollector(provider=_StaticProvider(), assets=["BTC"], timeframes=["1h"])

    signals = await collector.collect()

    assert signals[0].metadata["canonical_symbol"] == "BTC/USDT:USDT"


def test_rainbow_dockerfile_copies_shared_core_package() -> None:
    dockerfile = Path("rainbow.Dockerfile").read_text(encoding="utf-8")

    assert "COPY core ./core" in dockerfile
