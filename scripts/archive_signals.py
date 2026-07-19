"""Monatlicher Signal-Archiv-Export — Issue #99.

Exportiert Signale älter als N Tage als JSON-Archiv und löscht sie
anschließend aus der Hot-Tier (SQLite). Gedacht als Cron-Job am
1. jedes Monats um 03:00 UTC.

Verwendung:
    python scripts/archive_signals.py --days 30
    python scripts/archive_signals.py --dry-run --output-dir /tmp/archive
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from core.signals.envelope import CanonicalSignalEnvelope
from core.signals.registry import CanonicalSignalRegistry


def archive_old_signals(
    registry: CanonicalSignalRegistry,
    days: int = 30,
    *,
    dry_run: bool = False,
    output_dir: Path | str = "data/archive",
) -> tuple[int, Path | None]:
    """Alte Signale archivieren und aus der Hot-Tier entfernen.

    Parameter
    ----------
    registry : CanonicalSignalRegistry
        Die Signal-Registry (SQLite).
    days : int
        Signale älter als diese Anzahl Tage werden archiviert.
    dry_run : bool
        Wenn True, nur anzeigen — nicht löschen.
    output_dir : Path | str
        Zielverzeichnis für die Archiv-JSON-Datei.

    Returns
    -------
    tuple[int, Path | None]
        (Anzahl archivierter Signale, Pfad zur Archivdatei oder None)
    """
    cutoff = datetime.now(UTC) - timedelta(days=days)
    old_signals: list[CanonicalSignalEnvelope] = registry.get_signals_before(cutoff)

    if not old_signals:
        print(f"Keine Signale älter als {days} Tage gefunden (cutoff: {cutoff.isoformat()}).")
        return 0, None

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    archive_path = output_dir / f"signals_archive_{date_str}.json"

    envelopes_json = [sig.model_dump(mode="json") for sig in old_signals]

    archive_data = {
        "archive_date": date_str,
        "cutoff": cutoff.isoformat(),
        "signal_count": len(old_signals),
        "signals": envelopes_json,
    }

    archive_path.write_text(json.dumps(archive_data, indent=2, default=str), encoding="utf-8")
    print(f"Archiviert: {len(old_signals)} Signale → {archive_path}")

    if dry_run:
        print("[DRY-RUN] Keine Signale aus Hot-Tier gelöscht.")
    else:
        deleted = registry.delete_signals_before(cutoff)
        print(f"Gelöscht: {deleted} Signale aus Hot-Tier.")

    return len(old_signals), archive_path


def build_parser() -> argparse.ArgumentParser:
    """CLI-Argument-Parser für das Archiv-Script."""
    parser = argparse.ArgumentParser(
        description="Monatlicher Signal-Archiv-Export (Issue #99)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Signale älter als N Tage archivieren (default: 30)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Nur anzeigen, nicht aus Hot-Tier löschen",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/archive",
        help="Zielverzeichnis für Archiv-JSON (default: data/archive)",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="rainbow/storage/signals.db",
        help="Pfad zur Signal-Datenbank (default: rainbow/storage/signals.db)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI-Einstiegspunkt."""
    parser = build_parser()
    args = parser.parse_args(argv)

    registry = CanonicalSignalRegistry(db_path=args.db_path)
    try:
        count_before = registry.count()
        print(f"Signale in DB vor Archivierung: {count_before}")

        archived, archive_path = archive_old_signals(
            registry,
            days=args.days,
            dry_run=args.dry_run,
            output_dir=args.output_dir,
        )

        count_after = registry.count()
        print(f"Signale in DB nach Archivierung: {count_after}")
        print(f"Archiviert: {archived} | Verbleibend: {count_after}")

        return 0
    except Exception as exc:
        print(f"FEHLER: {exc}", file=sys.stderr)
        return 1
    finally:
        registry.close()


if __name__ == "__main__":
    sys.exit(main())
