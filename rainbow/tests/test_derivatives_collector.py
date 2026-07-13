import asyncio

from rainbow.collectors.derivatives_collector import DerivativesCollector
from rainbow.models.signal import Direction


class FakeResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self._data


class FakeClient:
    def __init__(self, funding="0.0001", oi="100"):
        self.funding = funding
        self.oi = oi

    async def get(self, url, params):
        if "premiumIndex" in url:
            return FakeResponse({"lastFundingRate": self.funding})
        if "openInterest" in url:
            return FakeResponse({"openInterest": self.oi})
        return FakeResponse([{"longShortRatio": "1.0"}])


def test_positive_extreme_funding_creates_bearish_signal():
    collector = DerivativesCollector(["BTC/USDT:USDT"], client=FakeClient(funding="0.0006"))
    signals = asyncio.run(collector.collect())
    assert signals[0].direction == Direction.BEARISH
    assert signals[0].metadata["subtype"] == "FUNDING_EXTREME_POSITIVE"


def test_negative_extreme_funding_creates_bullish_signal():
    collector = DerivativesCollector(["BTC/USDT:USDT"], client=FakeClient(funding="-0.0004"))
    signals = asyncio.run(collector.collect())
    assert signals[0].direction == Direction.BULLISH
    assert signals[0].metadata["subtype"] == "FUNDING_EXTREME_NEGATIVE"


def test_normal_funding_creates_no_signal():
    collector = DerivativesCollector(["BTC/USDT:USDT"], client=FakeClient(funding="0.0001"))
    assert asyncio.run(collector.collect()) == []


def test_oi_spike_creates_risk_signal(monkeypatch):
    collector = DerivativesCollector(["BTC/USDT:USDT"], client=FakeClient(oi="200"))

    async def fake_average(symbol, current_oi):
        return 100.0

    monkeypatch.setattr(collector, "_get_oi_24h_average", fake_average)
    signals = asyncio.run(collector.collect())
    assert signals[0].direction == Direction.NEUTRAL
    assert signals[0].metadata["subtype"] == "OI_SPIKE"


def test_symbol_mapping():
    assert DerivativesCollector.map_symbol("BTC/USDT:USDT") == "BTCUSDT"
