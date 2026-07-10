"""Adapters to convert legacy / rainbow signals into canonical envelopes."""

from __future__ import annotations

from datetime import UTC, datetime

from core.signal_model import Signal
from core.signals.envelope import (
    Actionability,
    CanonicalSignalEnvelope,
    DataQuality,
    DataQualityStatus,
    SignalClass,
    SignalDirection,
    SignalPriority,
)

# ---------------------------------------------------------------------------
# Lazy import helpers — rainbow is an optional subsystem
# ---------------------------------------------------------------------------

def _get_rainbow_crypto_signal():
    from rainbow.models.signal import CryptoSignal
    return CryptoSignal


# ---------------------------------------------------------------------------
# Mapping helpers
# ---------------------------------------------------------------------------

_ACTION_DIRECTION: dict[str, SignalDirection] = {
    "BUY": SignalDirection.BULLISH,
    "SELL": SignalDirection.BEARISH,
    "HOLD": SignalDirection.NEUTRAL,
}


def _feed_health_to_status(feed_health: dict | None) -> DataQualityStatus:
    """Best-effort mapping of legacy feed_health → DataQualityStatus."""
    if feed_health is None:
        return DataQualityStatus.OK
    status = feed_health.get("status", "ok")
    mapping = {
        "ok": DataQualityStatus.OK,
        "degraded": DataQualityStatus.DEGRADED,
        "stale": DataQualityStatus.STALE,
        "unavailable": DataQualityStatus.UNAVAILABLE,
    }
    return mapping.get(status, DataQualityStatus.OK)


def _rainbow_signal_type_to_class(signal_type) -> SignalClass:
    """Map rainbow SignalType → canonical SignalClass."""
    type_name = signal_type.value if hasattr(signal_type, "value") else str(signal_type)
    mapping = {
        "technical": SignalClass.ENTRY,
        "sentiment": SignalClass.ENTRY,
        "news": SignalClass.ENTRY,
        "onchain": SignalClass.ENTRY,
        "prediction_market": SignalClass.ENTRY,
        "macro": SignalClass.REGIME,
        "social": SignalClass.ENTRY,
        SignalClass.ENTRY: SignalClass.ENTRY,
    }
    return mapping.get(type_name, SignalClass.ENTRY)


# ---------------------------------------------------------------------------
# Public adapter functions
# ---------------------------------------------------------------------------

def from_legacy_signal(
    signal: Signal,
    market_context: dict | None = None,
) -> CanonicalSignalEnvelope:
    """Convert a core.signal_model.Signal into a CanonicalSignalEnvelope.

    Parameters
    ----------
    signal : Signal
        The legacy signal dataclass.
    market_context : dict, optional
        Extra context — expected keys: ``risk_score`` (float 0-1),
        ``feed_health`` (dict with ``status`` key), ``timeframe`` (str),
        ``priority`` (str), ``features`` (dict).
    """
    ctx = market_context or {}

    direction = _ACTION_DIRECTION.get(signal.action.upper(), SignalDirection.NEUTRAL)
    confidence = signal.confidence / 100.0 if signal.confidence > 1 else float(signal.confidence)
    risk_score = float(ctx.get("risk_score", 0.5))
    feed_health = ctx.get("feed_health")
    dq_status = _feed_health_to_status(feed_health)

    return CanonicalSignalEnvelope(
        signal_class=SignalClass.ENTRY,
        subtype="legacy",
        source="core.signal_model",
        asset=signal.pair,
        timeframe=ctx.get("timeframe"),
        created_at=datetime.fromtimestamp(signal.timestamp, tz=UTC) if signal.timestamp else datetime.now(UTC),
        direction=direction,
        confidence=confidence,
        risk_score=risk_score,
        priority=SignalPriority(ctx.get("priority", "medium")),
        reason_codes=[],
        features=ctx.get("features", {}),
        data_quality=DataQuality(
            status=dq_status,
            source_latency_ms=ctx.get("source_latency_ms"),
            source_quality=ctx.get("source_quality"),
            freshness_seconds=ctx.get("freshness_seconds"),
        ),
        actionability=Actionability(can_alert=True),
        invalidation={"max_age_seconds": 3600, "conditions": []},
        raw_refs=[],
    )


def from_rainbow_signal(
    signal,
    risk_score: float = 0.5,
) -> CanonicalSignalEnvelope:
    """Convert a rainbow CryptoSignal into a CanonicalSignalEnvelope.

    Parameters
    ----------
    signal : CryptoSignal
        The rainbow Pydantic signal model.
    risk_score : float
        External risk assessment (0-1).
    """
    _get_rainbow_crypto_signal()  # ensure rainbow is importable

    # direction mapping
    direction = SignalDirection.NEUTRAL
    if signal.direction is not None:
        dir_map = {
            "bullish": SignalDirection.BULLISH,
            "bearish": SignalDirection.BEARISH,
            "neutral": SignalDirection.NEUTRAL,
        }
        direction = dir_map.get(str(signal.direction.value), SignalDirection.NEUTRAL)

    sig_class = _rainbow_signal_type_to_class(signal.signal_type)
    metadata = signal.metadata or {}
    canonical_symbol = metadata.get("canonical_symbol")
    asset = canonical_symbol if isinstance(canonical_symbol, str) and canonical_symbol else signal.asset
    timeframe = metadata.get("timeframe")

    return CanonicalSignalEnvelope(
        signal_class=sig_class,
        subtype=signal.signal_type.value if signal.signal_type else "unknown",
        source=f"rainbow:{signal.source}",
        asset=asset,
        timeframe=timeframe if isinstance(timeframe, str) else None,
        created_at=signal.timestamp,
        direction=direction,
        confidence=signal.strength,
        risk_score=risk_score,
        priority=SignalPriority.MEDIUM,
        reason_codes=[],
        features=metadata,
        data_quality=DataQuality(
            status=DataQualityStatus.OK,
            source_latency_ms=None,
            source_quality=None,
            freshness_seconds=None,
        ),
        actionability=Actionability(can_alert=True),
        invalidation={"max_age_seconds": 3600, "conditions": []},
        raw_refs=[signal.signal_id],
    )
