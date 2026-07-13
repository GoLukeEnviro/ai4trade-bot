from datetime import UTC, datetime, timedelta

from core.signals.envelope import (
    Actionability,
    CanonicalSignalEnvelope,
    DataQuality,
    DataQualityStatus,
    SignalClass,
    SignalDirection,
)
from core.signals.registry import CanonicalSignalRegistry


def _env(asset="BTC", created_at=None):
    return CanonicalSignalEnvelope(
        **{"class": SignalClass.RISK},
        subtype="test",
        source="pytest",
        asset=asset,
        created_at=created_at or datetime.now(UTC),
        direction=SignalDirection.NEUTRAL,
        confidence=0.5,
        risk_score=0.2,
        data_quality=DataQuality(status=DataQualityStatus.OK),
        actionability=Actionability(can_alert=True),
    )


def test_count_returns_inserted_rows(tmp_path):
    registry = CanonicalSignalRegistry(str(tmp_path / "signals.db"))
    try:
        for i in range(5):
            registry.append(_env(asset=f"ASSET{i}"))
        assert registry.count() == 5
    finally:
        registry.close()


def test_count_returns_zero_for_empty_registry(tmp_path):
    registry = CanonicalSignalRegistry(str(tmp_path / "signals.db"))
    try:
        assert registry.count() == 0
    finally:
        registry.close()


def test_get_signals_in_range_filters_asset_and_time(tmp_path):
    registry = CanonicalSignalRegistry(str(tmp_path / "signals.db"))
    now = datetime.now(UTC)
    try:
        registry.append(_env("BTC", now - timedelta(hours=2)))
        expected = _env("BTC", now)
        registry.append(expected)
        registry.append(_env("ETH", now))
        rows = registry.get_signals_in_range("BTC", now - timedelta(minutes=1), now + timedelta(minutes=1))
        assert [row.id for row in rows] == [expected.id]
    finally:
        registry.close()


def test_get_and_delete_signals_before(tmp_path):
    registry = CanonicalSignalRegistry(str(tmp_path / "signals.db"))
    now = datetime.now(UTC)
    try:
        old = _env("BTC", now - timedelta(days=2))
        registry.append(old)
        registry.append(_env("BTC", now))
        cutoff = now - timedelta(days=1)
        assert [row.id for row in registry.get_signals_before(cutoff)] == [old.id]
        assert registry.delete_signals_before(cutoff) == 1
        assert registry.count() == 1
    finally:
        registry.close()
