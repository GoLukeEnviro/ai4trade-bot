"""Outcome tracker CLI — manual runner for signal outcome evaluation.

Usage:
    python -m core.outcome_tracker --once
    python -m core.outcome_tracker --once --dry-run
    python -m core.outcome_tracker --once --window-seconds 7200 --min-move-pct 0.3
    python -m core.outcome_tracker --daemon --interval 300
    python -m core.outcome_tracker --daemon --interval 60 --dry-run

This is an observational tool. It never triggers trades or strategy changes.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from typing import Any

from core.heartbeat_writer import HeartbeatWriter
from core.outcomes.evaluator import OutcomeEvaluator
from core.outcomes.price_provider import PriceProvider, StaticPriceProvider
from core.outcomes.repository import OutcomeRepository
from core.signals.registry import CanonicalSignalRegistry

log = logging.getLogger(__name__)

_HEARTBEAT_PATH = "storage/outcome_tracker.heartbeat"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="core.outcome_tracker",
        description="Evaluate past signals against price movement (observational only).",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        default=True,
        help="Run one evaluation pass and exit (default).",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        default=False,
        help="Loop forever, running evaluation every --interval seconds.",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=300,
        help="Seconds between evaluation runs in daemon mode (default: 300).",
    )
    parser.add_argument(
        "--db-path",
        default="storage/outcomes.db",
        help="Path to outcomes SQLite database (default: storage/outcomes.db).",
    )
    parser.add_argument(
        "--signal-db-path",
        default="storage/canonical_signals.db",
        help="Path to canonical signals SQLite database.",
    )
    parser.add_argument(
        "--window-seconds",
        type=int,
        default=3600,
        help="Evaluation window in seconds (default: 3600).",
    )
    parser.add_argument(
        "--min-move-pct",
        type=float,
        default=0.5,
        help="Minimum %% price move for win/loss classification (default: 0.5).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Max signals to evaluate per run (default: 100).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Evaluate without persisting outcomes.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level (default: INFO).",
    )
    return parser


def run(
    *,
    db_path: str = "storage/outcomes.db",
    signal_db_path: str = "storage/canonical_signals.db",
    window_seconds: int = 3600,
    min_move_pct: float = 0.5,
    limit: int = 100,
    dry_run: bool = False,
    price_provider: PriceProvider | None = None,
    _signal_registry: CanonicalSignalRegistry | None = None,
    _outcome_repo: OutcomeRepository | None = None,
) -> dict[str, Any]:
    """Run one evaluation pass.

    Returns a summary dict with stats and any errors.
    """
    signal_registry = _signal_registry or CanonicalSignalRegistry(signal_db_path)
    outcome_repo = _outcome_repo or OutcomeRepository(db_path)
    prices = price_provider or StaticPriceProvider(default=0.0)

    evaluator = OutcomeEvaluator(
        outcome_repo=outcome_repo,
        price_provider=prices,
        evaluation_window_seconds=window_seconds,
        min_move_pct=min_move_pct,
    )

    # Find signals ready for evaluation
    open_signals = signal_registry.query_open(
        min_age_seconds=window_seconds,
        limit=limit,
    )
    log.info("Found %d open signals eligible for evaluation", len(open_signals))

    if not open_signals:
        return {"evaluated": 0, "skipped": 0, "errors": 0, "total_open": 0}

    stats = evaluator.evaluate_batch(open_signals, dry_run=dry_run)
    stats["total_open"] = len(open_signals)

    # Summary
    log.info(
        "Outcome evaluation complete: %d evaluated, %d skipped, %d errors (dry_run=%s)",
        stats["evaluated"],
        stats["skipped"],
        stats["errors"],
        dry_run,
    )

    return stats


def run_daemon(
    *,
    interval: int = 300,
    db_path: str = "storage/outcomes.db",
    signal_db_path: str = "storage/canonical_signals.db",
    window_seconds: int = 3600,
    min_move_pct: float = 0.5,
    limit: int = 100,
    dry_run: bool = False,
    heartbeat_path: str = _HEARTBEAT_PATH,
    max_cycles: int = 0,
    _time_module: Any = None,
) -> None:
    """Run outcome evaluation in a loop with heartbeat.

    Args:
        interval: Seconds between evaluation runs.
        max_cycles: Maximum number of cycles before exiting (0 = run forever).
        _time_module: Injectable time module for testing (defaults to ``time``).
    """
    tm = _time_module or time
    shutdown = False

    def _handle_signal(signum: int, frame: Any) -> None:
        nonlocal shutdown
        log.info("Received signal %d, shutting down gracefully", signum)
        shutdown = True

    original_sigterm = signal.getsignal(signal.SIGTERM)
    original_sigint = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    hb = HeartbeatWriter(path=heartbeat_path, component="outcome_tracker")

    cycle = 0
    try:
        while not shutdown:
            cycle += 1
            log.info("Daemon cycle starting (cycle=%d)", cycle)
            result = run(
                db_path=db_path,
                signal_db_path=signal_db_path,
                window_seconds=window_seconds,
                min_move_pct=min_move_pct,
                limit=limit,
                dry_run=dry_run,
            )
            hb.write(
                status="healthy",
                evaluated=result.get("evaluated", 0),
                errors=result.get("errors", 0),
            )
            log.info("Daemon cycle %d complete, sleeping %ds", cycle, interval)
            if max_cycles and cycle >= max_cycles:
                log.info("Reached max_cycles=%d, exiting daemon", max_cycles)
                break
            if shutdown:
                break
            tm.sleep(interval)
    except KeyboardInterrupt:
        log.info("KeyboardInterrupt received, shutting down gracefully")
    finally:
        signal.signal(signal.SIGTERM, original_sigterm)
        signal.signal(signal.SIGINT, original_sigint)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.daemon:
        log.info("Outcome Tracker starting in daemon mode (interval=%ds, dry_run=%s)", args.interval, args.dry_run)
        run_daemon(
            interval=args.interval,
            db_path=args.db_path,
            signal_db_path=args.signal_db_path,
            window_seconds=args.window_seconds,
            min_move_pct=args.min_move_pct,
            limit=args.limit,
            dry_run=args.dry_run,
        )
    else:
        log.info("Outcome Tracker starting (dry_run=%s)", args.dry_run)
        result = run(
            db_path=args.db_path,
            signal_db_path=args.signal_db_path,
            window_seconds=args.window_seconds,
            min_move_pct=args.min_move_pct,
            limit=args.limit,
            dry_run=args.dry_run,
        )
        print(f"Outcome evaluation complete: {result}")

        if result["errors"] > 0:
            sys.exit(1)


if __name__ == "__main__":
    main()
