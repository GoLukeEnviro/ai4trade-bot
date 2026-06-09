"""Tests for rainbow.processor.store — SignalStore (async, aiosqlite)."""

import pathlib

import pytest

from rainbow.models.signal import CryptoSignal, Direction, SignalType
from rainbow.processor.store import SignalStore


@pytest.fixture
async def store(tmp_path) -> SignalStore:
    """Create and start a SignalStore with a temp database."""
    db_path = str(tmp_path / "test_signals.db")
    s = SignalStore(db_path=db_path)
    await s.start()
    yield s
    await s.stop()


def _make_signal(
    asset: str = "BTC",
    signal_type: SignalType = SignalType.TECHNICAL,
    direction: Direction = Direction.BULLISH,
    strength: float = 0.8,
    source: str = "test_source",
) -> CryptoSignal:
    return CryptoSignal(
        source=source,
        asset=asset,
        signal_type=signal_type,
        direction=direction,
        strength=strength,
        confidence=0.7,
    )


class TestSignalStoreConstruction:
    def test_default_path(self) -> None:
        store = SignalStore()
        assert store._db_path == "rainbow/storage/signals.db"
        assert store._conn is None

    def test_custom_path(self) -> None:
        store = SignalStore(db_path="/tmp/test.db")
        assert store._db_path == "/tmp/test.db"


class TestSignalStoreSaveAndGet:
    async def test_save_and_get_by_id(self, store: SignalStore) -> None:
        signal = _make_signal()
        await store.save(signal)
        result = await store.get_by_id(signal.signal_id)
        assert result is not None
        assert result["asset"] == "BTC"
        assert result["source"] == "test_source"

    async def test_get_by_id_not_found(self, store: SignalStore) -> None:
        result = await store.get_by_id("nonexistent_id")
        assert result is None

    async def test_save_duplicate_id_ignored(self, store: SignalStore) -> None:
        signal = _make_signal()
        await store.save(signal)
        # Saving the same signal again should not fail (INSERT OR IGNORE)
        await store.save(signal)


class TestSignalStoreGetLatest:
    async def test_get_latest_empty(self, store: SignalStore) -> None:
        results = await store.get_latest()
        assert results == []

    async def test_get_latest_all(self, store: SignalStore) -> None:
        s1 = _make_signal(asset="BTC")
        s2 = _make_signal(asset="ETH")
        await store.save(s1)
        await store.save(s2)
        results = await store.get_latest()
        assert len(results) == 2

    async def test_get_latest_filter_by_asset(self, store: SignalStore) -> None:
        s1 = _make_signal(asset="BTC")
        s2 = _make_signal(asset="ETH")
        await store.save(s1)
        await store.save(s2)
        results = await store.get_latest(asset="BTC")
        assert len(results) == 1
        assert results[0]["asset"] == "BTC"

    async def test_get_latest_filter_by_source(self, store: SignalStore) -> None:
        s1 = _make_signal(source="ta")
        s2 = _make_signal(source="news")
        await store.save(s1)
        await store.save(s2)
        results = await store.get_latest(source="ta")
        assert len(results) == 1
        assert results[0]["source"] == "ta"

    async def test_get_latest_with_limit(self, store: SignalStore) -> None:
        for i in range(10):
            sig = _make_signal(asset=f"ASSET{i}")
            await store.save(sig)
        results = await store.get_latest(limit=3)
        assert len(results) == 3


class TestSignalStoreStartStop:
    async def test_start_creates_directory(self, tmp_path: pathlib.Path) -> None:

        db_path = str(tmp_path / "subdir" / "test.db")
        store = SignalStore(db_path=db_path)
        await store.start()
        assert store._conn is not None
        await store.stop()
        assert store._conn is None

    async def test_stop_idempotent(self, store: SignalStore) -> None:
        await store.stop()
        await store.stop()  # Should not raise
        assert store._conn is None
