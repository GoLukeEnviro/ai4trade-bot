"""Deterministic, side-effect-free canonical signal replay helpers."""

from __future__ import annotations

from collections.abc import Iterable

from core.signals.envelope import CanonicalSignalEnvelope, DataQualityStatus, SignalDirection


def eligible_signals(
    signals: Iterable[CanonicalSignalEnvelope],
    confidence_gate: float = 0.65,
) -> list[CanonicalSignalEnvelope]:
    """Return chronological signals which are eligible for a simulated trade.

    This deliberately has no exchange or order-management integration.  A
    canonical signal only becomes an input for historical simulation here.
    """
    return sorted(
        (
            signal
            for signal in signals
            if signal.confidence >= confidence_gate
            and signal.direction in (SignalDirection.BULLISH, SignalDirection.BEARISH)
            and signal.data_quality.status == DataQualityStatus.OK
        ),
        key=lambda signal: signal.created_at,
    )
