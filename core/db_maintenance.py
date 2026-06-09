"""Database maintenance CLI — vacuum and cleanup for all SQLite databases.

Run as: python -m core.db_maintenance
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)

_DEFAULT_REGISTRY_DB = "storage/canonical_signals.db"
_DEFAULT_OUTCOMES_DB = "storage/outcomes.db"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Database maintenance: vacuum and cleanup for ai4trade-bot SQLite databases.",
    )
    parser.add_argument(
        "--vacuum",
        action="store_true",
        help="Run VACUUM on all databases to reclaim space.",
    )
    parser.add_argument(
        "--cleanup-registry",
        type=int,
        default=None,
        metavar="HOURS",
        help="Cleanup registry entries older than H hours.",
    )
    parser.add_argument(
        "--cleanup-outcomes",
        type=int,
        default=None,
        metavar="DAYS",
        help="Cleanup outcome entries older than D days.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all cleanup operations with defaults (registry=24h, outcomes=30d, vacuum).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point for the db_maintenance CLI."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = _build_parser()
    args = parser.parse_args(argv)

    # If nothing requested, show help
    if not args.vacuum and args.cleanup_registry is None and args.cleanup_outcomes is None and not args.all:
        parser.print_help()
        return 0

    errors = 0

    # ---- Registry ----
    registry_path = Path(_DEFAULT_REGISTRY_DB)
    if args.cleanup_registry is not None or args.all:
        hours = args.cleanup_registry if args.cleanup_registry is not None else 24
        if registry_path.exists():
            try:
                from core.signals.registry import CanonicalSignalRegistry

                reg = CanonicalSignalRegistry(db_path=str(registry_path))
                deleted = reg.cleanup_expired(max_age_hours=hours)
                print(f"registry: deleted {deleted} signals older than {hours}h")
                log.info("registry: deleted %d signals older than %dh", deleted, hours)
                reg.close()
            except Exception as exc:
                log.error("registry cleanup failed: %s", exc)
                errors += 1
        else:
            print("registry: DB file not found, skipping")
            log.info("registry: DB file not found at %s, skipping", registry_path)

    # ---- Outcomes ----
    outcomes_path = Path(_DEFAULT_OUTCOMES_DB)
    if args.cleanup_outcomes is not None or args.all:
        days = args.cleanup_outcomes if args.cleanup_outcomes is not None else 30
        if outcomes_path.exists():
            try:
                from core.outcomes.repository import OutcomeRepository

                repo = OutcomeRepository(db_path=str(outcomes_path))
                deleted = repo.cleanup_old(max_age_days=days)
                print(f"outcomes: deleted {deleted} outcomes older than {days}d")
                log.info("outcomes: deleted %d outcomes older than %dd", deleted, days)
                repo.close()
            except Exception as exc:
                log.error("outcomes cleanup failed: %s", exc)
                errors += 1
        else:
            print("outcomes: DB file not found, skipping")
            log.info("outcomes: DB file not found at %s, skipping", outcomes_path)

    # ---- Vacuum ----
    if args.vacuum or args.all:
        for label, path in [("registry", registry_path), ("outcomes", outcomes_path)]:
            if not path.exists():
                print(f"{label}: DB file not found, skipping vacuum")
                log.info("%s: DB file not found at %s, skipping vacuum", label, path)
                continue
            try:
                if label == "registry":
                    from core.signals.registry import CanonicalSignalRegistry

                    db = CanonicalSignalRegistry(db_path=str(path))
                else:
                    from core.outcomes.repository import OutcomeRepository

                    db = OutcomeRepository(db_path=str(path))
                db.vacuum()
                print(f"{label}: VACUUM complete")
                log.info("%s: VACUUM complete", label)
                db.close()
            except Exception as exc:
                log.error("%s vacuum failed: %s", label, exc)
                errors += 1

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
