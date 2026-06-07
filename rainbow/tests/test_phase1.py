import pandas as pd
import pytest
from httpx import ASGITransport, AsyncClient

from rainbow.collectors.ta_collector import TACollector
from rainbow.config.settings import RainbowSettings
from rainbow.distribution.api import create_app
from rainbow.models.signal import CryptoSignal, Direction, SignalType
from rainbow.processor.scorer import RainbowScorer
from rainbow.processor.store import SignalStore


def _make_ohlcv(n: int = 100, base_price: float = 50000.0) -> pd.DataFrame:
    rows = []
    for i in range(n):
        price = base_price + i * 10 + (i % 7) * 50
        rows.append(
            {
                "timestamp": 1700000000.0 + i * 3600,
                "open": price - 50,
                "high": price + 200,
                "low": price - 200,
                "close": price,
                "volume": 1000.0 + i * 10,
            }
        )
    return pd.DataFrame(rows)


class FakeProvider:
    async def get_ohlcv(self, symbol: str, interval: str = "1h", limit: int = 200) -> pd.DataFrame:
        return _make_ohlcv(min(limit, 200))

    async def get_price(self, symbol: str) -> float:
        return 50000.0


class TestTACollector:
    @pytest.fixture
    def provider(self):
        return FakeProvider()

    @pytest.fixture
    def collector(self, provider):
        return TACollector(provider=provider, assets=["BTC", "ETH"], timeframes=["1h"])

    def test_name(self, collector):
        assert collector.name == "ta"

    @pytest.mark.anyio
    async def test_collect_produces_signals(self, collector):
        signals = await collector.collect()
        assert len(signals) == 2  # BTC + ETH
        for sig in signals:
            assert isinstance(sig, CryptoSignal)
            assert sig.signal_type == SignalType.TECHNICAL
            assert sig.source == "ta_1h"
            assert sig.strength >= 0.0
            assert sig.confidence >= 0.0
            assert sig.raw_data is not None
            assert "rsi" in sig.raw_data

    @pytest.mark.anyio
    async def test_multi_timeframe(self, provider):
        col = TACollector(provider=provider, assets=["BTC"], timeframes=["1h", "4h"])
        signals = await col.collect()
        assert len(signals) == 2
        sources = {s.source for s in signals}
        assert "ta_1h" in sources
        assert "ta_4h" in sources

    @pytest.mark.anyio
    async def test_direction_mapping(self, provider):
        col = TACollector(provider=provider, assets=["BTC"], timeframes=["1h"])
        signals = await col.collect()
        assert signals[0].direction in (Direction.BULLISH, Direction.BEARISH, Direction.NEUTRAL)


class TestRainbowScorer:
    def test_score_bullish_signals(self):
        signals = [
            CryptoSignal(
                source="ta_1h",
                asset="BTC",
                signal_type=SignalType.TECHNICAL,
                direction=Direction.BULLISH,
                strength=0.8,
                confidence=0.7,
            ),
        ]
        scorer = RainbowScorer()
        scored = scorer.score(signals)
        assert len(scored) == 1
        assert scored[0].rainbow_score is not None
        assert scored[0].rainbow_score > 0.0

    def test_score_mixed_signals(self):
        signals = [
            CryptoSignal(
                source="ta_1h",
                asset="BTC",
                signal_type=SignalType.TECHNICAL,
                direction=Direction.BULLISH,
                strength=0.8,
                confidence=0.7,
            ),
            CryptoSignal(
                source="x_sentiment",
                asset="BTC",
                signal_type=SignalType.SOCIAL,
                direction=Direction.BEARISH,
                strength=0.6,
                confidence=0.5,
            ),
        ]
        scorer = RainbowScorer()
        scored = scorer.score(signals)
        assert all(s.rainbow_score is not None for s in scored)
        assert scored[0].rainbow_score == scored[1].rainbow_score

    def test_score_empty(self):
        scorer = RainbowScorer()
        assert scorer.score([]) == []

    def test_custom_weights(self):
        scorer = RainbowScorer(weights={"technical": 1.0})
        signals = [
            CryptoSignal(
                source="ta",
                asset="BTC",
                signal_type=SignalType.TECHNICAL,
                direction=Direction.BULLISH,
                strength=0.9,
                confidence=0.8,
            ),
        ]
        scored = scorer.score(signals)
        assert scored[0].rainbow_score == pytest.approx(0.9, abs=0.01)


class TestSignalStore:
    @pytest.mark.anyio
    async def test_save_and_retrieve(self):
        store = SignalStore(":memory:")
        await store.start()

        signal = CryptoSignal(
            source="ta_1h",
            asset="BTC",
            signal_type=SignalType.TECHNICAL,
            direction=Direction.BULLISH,
            strength=0.72,
            confidence=0.65,
        )
        await store.save(signal)

        results = await store.get_latest(asset="BTC")
        assert len(results) == 1
        assert results[0]["asset"] == "BTC"
        assert results[0]["source"] == "ta_1h"

        await store.stop()

    @pytest.mark.anyio
    async def test_get_by_id(self):
        store = SignalStore(":memory:")
        await store.start()

        signal = CryptoSignal(
            source="ta_1h",
            asset="ETH",
            signal_type=SignalType.TECHNICAL,
            direction=Direction.BEARISH,
            strength=0.3,
            confidence=0.4,
        )
        await store.save(signal)

        found = await store.get_by_id(signal.signal_id)
        assert found is not None
        assert found["asset"] == "ETH"

        missing = await store.get_by_id("nonexistent")
        assert missing is None

        await store.stop()

    @pytest.mark.anyio
    async def test_filter_by_source(self):
        store = SignalStore(":memory:")
        await store.start()

        for src in ["ta_1h", "ta_4h", "x_sentiment"]:
            await store.save(
                CryptoSignal(
                    source=src,
                    asset="BTC",
                    signal_type=SignalType.TECHNICAL,
                    strength=0.5,
                    confidence=0.5,
                )
            )

        results = await store.get_latest(source="ta_1h")
        assert len(results) == 1
        assert results[0]["source"] == "ta_1h"

        await store.stop()


class TestAPI:
    @pytest.fixture
    async def app_and_store(self):
        store = SignalStore(":memory:")
        await store.start()
        settings = RainbowSettings(db_path=":memory:")
        app = create_app(store=store, settings=settings, enable_metrics=False)
        return app, store

    @pytest.mark.anyio
    async def test_health_endpoint(self, app_and_store):
        app, store = app_and_store
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "healthy"

    @pytest.mark.anyio
    async def test_signals_latest_empty(self, app_and_store):
        app, store = app_and_store
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/signals/latest")
            assert resp.status_code == 200
            assert resp.json() == []

    @pytest.mark.anyio
    async def test_signals_latest_with_data(self, app_and_store):
        app, store = app_and_store
        await store.save(
            CryptoSignal(
                source="ta_1h",
                asset="BTC",
                signal_type=SignalType.TECHNICAL,
                direction=Direction.BULLISH,
                strength=0.72,
                confidence=0.65,
            )
        )
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/signals/latest")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 1
            assert data[0]["asset"] == "BTC"

    @pytest.mark.anyio
    async def test_signal_by_id(self, app_and_store):
        app, store = app_and_store
        sig = CryptoSignal(
            source="ta_1h",
            asset="BTC",
            signal_type=SignalType.TECHNICAL,
            strength=0.5,
            confidence=0.5,
        )
        await store.save(sig)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/signals/{sig.signal_id}")
            assert resp.status_code == 200
            assert resp.json()["signal_id"] == sig.signal_id

    @pytest.mark.anyio
    async def test_signal_not_found(self, app_and_store):
        app, store = app_and_store
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/signals/nonexistent")
            assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_signals_ingest_creates_signal(self, app_and_store):
        app, store = app_and_store
        payload = {
            "asset": "BTCUSDT",
            "source": "legacy_strategy",
            "signal_type": "technical",
            "direction": "bullish",
            "strength": 0.75,
            "confidence": 0.80,
            "value": 50000.0,
            "raw_data": {"pair": "BTC/USDT"},
            "metadata": {"confidence_raw": 80},
        }
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/signals/ingest", json=payload)
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
            assert "signal_id" in data

            # Verify signal is retrievable via GET /signals/latest
            resp2 = await client.get("/signals/latest")
            assert resp2.status_code == 200
            signals = resp2.json()
            assert len(signals) == 1
            assert signals[0]["asset"] == "BTCUSDT"

    @pytest.mark.anyio
    async def test_signals_ingest_with_invalid_direction_defaults_neutral(self, app_and_store):
        app, store = app_and_store
        payload = {
            "asset": "ETHUSDT",
            "source": "test",
            "signal_type": "technical",
            "direction": "sideways",
            "strength": 0.5,
            "confidence": 0.5,
        }
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/signals/ingest", json=payload)
            assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_signals_ingest_minimal_payload(self, app_and_store):
        app, store = app_and_store
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/signals/ingest", json={})
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
