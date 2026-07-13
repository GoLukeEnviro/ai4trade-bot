"""Tests for Rainbow's JSON metrics endpoint."""

from fastapi.testclient import TestClient

from rainbow.config.settings import RainbowSettings
from rainbow.distribution.api import create_app
from rainbow.models.signal import CryptoSignal, Direction, SignalType
from rainbow.processor.store import SignalStore


async def test_metrics_signals_stored_count_reflects_actual_rows(tmp_path) -> None:
    """The metrics endpoint reports the total number of stored signals."""
    store = SignalStore(str(tmp_path / "signals.db"))
    await store.start()
    try:
        for asset in ("BTC", "ETH", "SOL"):
            await store.save(
                CryptoSignal(
                    source="test",
                    asset=asset,
                    signal_type=SignalType.TECHNICAL,
                    direction=Direction.BULLISH,
                    strength=0.8,
                    confidence=0.7,
                )
            )

        app = create_app(store=store, settings=RainbowSettings(), enable_metrics=False)
        with TestClient(app) as client:
            response = client.get("/metrics")

        assert response.status_code == 200
        assert response.json()["signals_stored_count"] == 3
    finally:
        await store.stop()
