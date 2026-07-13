"""Canonical Rainbow envelopes must expose a measurable source freshness."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from core.signals.adapters import from_rainbow_signal
from rainbow.models.signal import CryptoSignal, Direction, SignalType


def test_rainbow_adapter_records_non_negative_source_freshness() -> None:
    signal = CryptoSignal(
        source="ta_1h",
        asset="BTC",
        signal_type=SignalType.TECHNICAL,
        direction=Direction.BULLISH,
        strength=0.7,
        confidence=0.7,
        value=100_000.0,
        timestamp=datetime.now(UTC) - timedelta(seconds=4),
    )

    envelope = from_rainbow_signal(signal)

    assert envelope.data_quality.freshness_seconds is not None
    assert 0 <= envelope.data_quality.freshness_seconds < 10
