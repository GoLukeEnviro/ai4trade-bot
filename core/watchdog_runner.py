# core/watchdog_runner.py
"""CLI entry point for running the watchdog as a standalone process.

Usage:
    python -m core.watchdog_runner
    python -m core.watchdog_runner --config config/watchdog.yaml
    python -m core.watchdog_runner --interval 60 --once

Scheduling strategy: separate CLI process (option 1 from issue #31).
This keeps watchdog decoupled from main trading loops and easy to
containerize as a Docker sidecar later.
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import time
from pathlib import Path
from typing import Any

from core.notifications.telegram_sink import TelegramSink
from core.watchdog import LogNotificationSink, Watchdog, WatchedComponent

log = logging.getLogger(__name__)

DEFAULT_INTERVAL = 60
DEFAULT_CONFIG_PATH = "config/watchdog.json"


def _build_sinks(config: dict[str, Any]) -> list:
    """Build notification sinks from config."""
    sinks: list = [LogNotificationSink()]

    telegram_cfg = config.get("telegram", {})
    if telegram_cfg:
        sink = TelegramSink(
            bot_token=telegram_cfg.get("bot_token"),
            chat_id=telegram_cfg.get("chat_id"),
            min_interval_seconds=telegram_cfg.get("min_interval_seconds", 60.0),
            dry_run=telegram_cfg.get("dry_run", False),
            http_timeout=telegram_cfg.get("http_timeout", 10.0),
        )
        sinks.append(sink)
        log.info(
            "TelegramSink added (configured=%s, dry_run=%s)",
            sink._is_configured(),
            telegram_cfg.get("dry_run", False),
        )

    return sinks


def _build_components(config: dict[str, Any]) -> list[WatchedComponent]:
    """Build watched components from config."""
    components = []
    for comp_cfg in config.get("components", []):
        comp = WatchedComponent(
            name=comp_cfg["name"],
            heartbeat_path=comp_cfg["heartbeat_path"],
            stale_threshold_seconds=comp_cfg.get("stale_threshold_seconds", 120.0),
            cooldown_seconds=comp_cfg.get("cooldown_seconds", 300.0),
        )
        components.append(comp)
        log.info("Watching: %s (%s)", comp.name, comp.heartbeat_path)

    return components


def load_config(config_path: str) -> dict[str, Any]:
    """Load watchdog config from JSON file."""
    path = Path(config_path)
    if not path.exists():
        log.warning("Config file not found: %s — using defaults", config_path)
        return _default_config()

    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        log.error("Failed to load config: %s — using defaults", e)
        return _default_config()


def _default_config() -> dict[str, Any]:
    """Default config watching legacy and rainbow heartbeats."""
    return {
        "components": [
            {
                "name": "legacy",
                "heartbeat_path": "storage/heartbeat.json",
                "stale_threshold_seconds": 120.0,
                "cooldown_seconds": 300.0,
            },
            {
                "name": "rainbow",
                "heartbeat_path": "storage/heartbeat_rainbow.json",
                "stale_threshold_seconds": 120.0,
                "cooldown_seconds": 300.0,
            },
        ],
        "telegram": {},
    }


def run_watchdog(
    config: dict[str, Any],
    interval: int = DEFAULT_INTERVAL,
    once: bool = False,
) -> None:
    """Main watchdog loop."""
    components = _build_components(config)
    if not components:
        log.error("No components to watch — exiting")
        sys.exit(1)

    sinks = _build_sinks(config)
    watchdog = Watchdog(components=components, sinks=sinks)

    log.info("Watchdog started (interval=%ds, components=%d)", interval, len(components))

    shutdown = False

    def _handle_signal(signum: int, _frame: Any) -> None:
        nonlocal shutdown
        log.info("Received signal %s — shutting down", signal.Signals(signum).name)
        shutdown = True

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    check_count = 0
    while not shutdown:
        check_count += 1
        alerts = watchdog.check_all()

        if alerts:
            log.info("Check #%d: %d alert(s)", check_count, len(alerts))
        else:
            log.debug("Check #%d: all healthy", check_count)

        if once:
            break

        # Sleep in small increments for responsive shutdown
        for _ in range(interval):
            if shutdown:
                break
            time.sleep(1)

    # Summary
    total_alerts = len(watchdog.alert_history)
    log.info("Watchdog stopped after %d checks, %d total alerts", check_count, total_alerts)

    # Log sink stats
    for sink in sinks:
        if hasattr(sink, "stats"):
            log.info("Sink %s stats: %s", type(sink).__name__, sink.stats)


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Watchdog runner — monitors heartbeat files and sends alerts",
    )
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help=f"Config file path (default: {DEFAULT_CONFIG_PATH})",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL,
        help=f"Check interval in seconds (default: {DEFAULT_INTERVAL})",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single check and exit",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level (default: INFO)",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    config = load_config(args.config)
    run_watchdog(config, interval=args.interval, once=args.once)


if __name__ == "__main__":
    main()
