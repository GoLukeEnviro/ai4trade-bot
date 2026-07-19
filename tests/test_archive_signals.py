"""Tests für scripts/archive_signals.py (Issue #99)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from core.signals.envelope import (
    CanonicalSignalEnvelope,
    DataQuality,
    DataQualityStatus,
    SignalClass,
    SignalDirection,
    SignalPriority,
)
from core.signals.registry import CanonicalSignalRegistry
from scripts.archive_signals import archive_old_signals, build_parser


def _make_envelope(
    *,
    asset: str = "BTC/USDT",
    created_at: datetime | None = None,
    signal_class: SignalClass = SignalClass.ENTRY,
) -> CanonicalSignalEnvelope:
    """Hilfsfunktion: CanonicalSignalEnvelope mit kontrollierten Werten."""
    envelope = CanonicalSignalEnvelope(
        signal_class=signal_class,
        subtype="test",
        source="test_source",
        asset=asset,
        direction=SignalDirection.BULLISH,
        confidence=0.7,
        risk_score=0.3,
        priority=SignalPriority.MEDIUM,
        data_quality=DataQuality(status=DataQualityStatus.OK),
        actionability={"can_alert": True},
        invalidation={"max_age_seconds": 3600, "conditions": []},
        raw_refs=[],
    )
    if created_at is not None:
        object.__setattr__(envelope, "created_at", created_at)
    return envelope


@pytest.fixture()
def registry(tmp_path: Path) -> Any:
    """Erzeugt eine temporäre CanonicalSignalRegistry."""
    db_path = str(tmp_path / "test_archive.db")
    reg = CanonicalSignalRegistry(db_path=db_path)
    yield reg
    reg.close()


class TestArchiveOldSignals:
    """Kern-Logik: archive_old_signals()."""

    def test_no_old_signals_returns_zero(self, registry: CanonicalSignalRegistry, tmp_path: Path) -> None:
        """Keine alten Signale → 0, kein Archiv."""
        count, path = archive_old_signals(registry, days=30, output_dir=tmp_path / "archive")
        assert count == 0
        assert path is None

    def test_archives_old_signals_and_deletes_from_hot_tier(
        self, registry: CanonicalSignalRegistry, tmp_path: Path
    ) -> None:
        """10 alte Signale → alle archiviert, 0 verbleiben in DB."""
        old_cutoff = datetime.now(timezone.utc) - timedelta(days=60)
        for i in range(10):
            env = _make_envelope(asset=f"BTC/USDT", created_at=old_cutoff)
            registry.append(env)

        assert registry.count() == 10

        output_dir = tmp_path / "archive"
        count, archive_path = archive_old_signals(registry, days=30, output_dir=output_dir)

        assert count == 10
        assert archive_path is not None
        assert archive_path.exists()

        # JSON-Archiv prüfen
        data = json.loads(archive_path.read_text(encoding="utf-8"))
        assert data["signal_count"] == 10
        assert len(data["signals"]) == 10
        assert "archive_date" in data
        assert "cutoff" in data

        # Jedes Signal muss alle Envelope-Felder enthalten
        for sig in data["signals"]:
            assert "id" in sig
            assert "asset" in sig
            assert "signal_class" in sig
            assert "direction" in sig
            assert "confidence" in sig
            assert "risk_score" in sig
            assert "data_quality" in sig
            assert "actionability" in sig

        # Hot-Tier muss leer sein
        assert registry.count() == 0

    def test_dry_run_does_not_delete(self, registry: CanonicalSignalRegistry, tmp_path: Path) -> None:
        """Dry-Run archiviert JSON, löscht aber nicht aus DB."""
        old_cutoff = datetime.now(timezone.utc) - timedelta(days=60)
        for i in range(5):
            env = _make_envelope(asset="ETH/USDT", created_at=old_cutoff)
            registry.append(env)

        assert registry.count() == 5

        output_dir = tmp_path / "archive"
        count, archive_path = archive_old_signals(
            registry, days=30, dry_run=True, output_dir=output_dir
        )

        assert count == 5
        assert archive_path is not None
        assert archive_path.exists()

        # Dry-Run: Signale bleiben in DB
        assert registry.count() == 5

    def test_recent_signals_not_archived(self, registry: CanonicalSignalRegistry, tmp_path: Path) -> None:
        """Nur alte Signale werden archiviert, neue bleiben."""
        old = datetime.now(timezone.utc) - timedelta(days=60)
        recent = datetime.now(timezone.utc) - timedelta(days=5)

        for i in range(3):
            registry.append(_make_envelope(asset="OLD", created_at=old))
        for i in range(2):
            registry.append(_make_envelope(asset="RECENT", created_at=recent))

        assert registry.count() == 5

        output_dir = tmp_path / "archive"
        count, archive_path = archive_old_signals(registry, days=30, output_dir=output_dir)

        assert count == 3
        assert registry.count() == 2  # Nur die neuen bleiben

    def test_archive_json_contains_full_envelope(self, registry: CanonicalSignalRegistry, tmp_path: Path) -> None:
        """Archiv-JSON enthält vollständige CanonicalSignalEnvelope-Daten."""
        old_cutoff = datetime.now(timezone.utc) - timedelta(days=60)
        env = _make_envelope(asset="SOL/USDT", created_at=old_cutoff)
        registry.append(env)

        output_dir = tmp_path / "archive"
        _, archive_path = archive_old_signals(registry, days=30, output_dir=output_dir)

        assert archive_path is not None
        data = json.loads(archive_path.read_text(encoding="utf-8"))
        sig = data["signals"][0]

        # Rekonstruktion via Pydantic muss fehlerfrei sein
        reconstructed = CanonicalSignalEnvelope.model_validate(sig)
        assert reconstructed.asset == "SOL/USDT"
        assert reconstructed.signal_class == SignalClass.ENTRY

    def test_custom_days_parameter(self, registry: CanonicalSignalRegistry, tmp_path: Path) -> None:
        """--days 7 archiviert nur Signale älter als 7 Tage."""
        very_old = datetime.now(timezone.utc) - timedelta(days=60)
        medium = datetime.now(timezone.utc) - timedelta(days=14)
        recent = datetime.now(timezone.utc) - timedelta(days=3)

        registry.append(_make_envelope(asset="V_OLD", created_at=very_old))
        registry.append(_make_envelope(asset="MEDIUM", created_at=medium))
        registry.append(_make_envelope(asset="RECENT", created_at=recent))

        output_dir = tmp_path / "archive"
        count, _ = archive_old_signals(registry, days=7, output_dir=output_dir)

        # very_old + medium sind >7 Tage, recent nicht
        assert count == 2
        assert registry.count() == 1


class TestCLIParser:
    """CLI-Argument-Parser."""

    def test_defaults(self) -> None:
        parser = build_parser()
        args = parser.parse_args([])
        assert args.days == 30
        assert args.dry_run is False
        assert args.output_dir == "data/archive"
        assert args.db_path == "rainbow/storage/signals.db"

    def test_custom_args(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--days", "7", "--dry-run", "--output-dir", "/tmp/arch"])
        assert args.days == 7
        assert args.dry_run is True
        assert args.output_dir == "/tmp/arch"

    def test_db_path_override(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--db-path", "/custom/signals.db"])
        assert args.db_path == "/custom/signals.db"
