"""Regression tests for ``SignalStore.count``."""

from rainbow.models.signal import CryptoSignal, Direction, SignalType
from rainbow.processor.store import SignalStore


def _signal(signal_id: str) -> CryptoSignal:
    return CryptoSignal(
        signal_id=signal_id,
        source="test",
        asset="BTC",
        signal_type=SignalType.TECHNICAL,
        direction=Direction.BULLISH,
        strength=0.8,
        confidence=0.7,
    )


async def test_count_is_zero_for_an_empty_store() -> None:
    store = SignalStore(":memory:")
    await store.start()
    try:
        assert await store.count() == 0
    finally:
        await store.stop()


async def test_count_increases_after_saving_a_signal() -> None:
    store = SignalStore(":memory:")
    await store.start()
    try:
        await store.save(_signal("signal-1"))

        assert await store.count() == 1
    finally:
        await store.stop()


async def test_count_excludes_duplicate_signal_ids() -> None:
    store = SignalStore(":memory:")
    await store.start()
    try:
        signal = _signal("duplicate")
        await store.save(signal)
        await store.save(signal)

        assert await store.count() == 1
    finally:
        await store.stop()
