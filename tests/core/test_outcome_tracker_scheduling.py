"""Tests for outcome tracker daemon/scheduling mode."""
from __future__ import annotations

import json
import os
import signal
import threading
import time
from unittest.mock import patch

from core.outcome_tracker import build_parser, run_daemon

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeTime:
    """Injectable time module that tracks sleep calls."""

    def __init__(self):
        self.sleep_calls: list[float] = []
        self._monotonic = 1000.0
        self._time = 1_700_000_000.0

    def sleep(self, seconds: float) -> None:
        self.sleep_calls.append(seconds)
        self._monotonic += seconds
        self._time += seconds

    def monotonic(self) -> float:
        return self._monotonic

    def time(self) -> float:
        return self._time


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_daemon_runs_multiple_cycles(tmp_path):
    """Daemon mode should invoke run() multiple times across cycles."""
    fake_time = FakeTime()
    heartbeat_file = tmp_path / "outcome_tracker.heartbeat"
    run_count = 0

    def mock_run(**kwargs):
        nonlocal run_count
        run_count += 1
        return {"evaluated": run_count, "skipped": 0, "errors": 0, "total_open": run_count}

    with patch("core.outcome_tracker.run", side_effect=mock_run):
        run_daemon(
            interval=60,
            heartbeat_path=str(heartbeat_file),
            max_cycles=3,
            _time_module=fake_time,
        )

    assert run_count == 3


def test_heartbeat_written_each_cycle(tmp_path):
    """Each daemon cycle should write a heartbeat file with expected fields."""
    fake_time = FakeTime()
    heartbeat_file = tmp_path / "outcome_tracker.heartbeat"
    cycle = 0

    def mock_run(**kwargs):
        nonlocal cycle
        cycle += 1
        return {"evaluated": cycle, "skipped": 0, "errors": 0}

    with patch("core.outcome_tracker.run", side_effect=mock_run):
        run_daemon(
            interval=30,
            heartbeat_path=str(heartbeat_file),
            max_cycles=2,
            _time_module=fake_time,
        )

    # Read the final heartbeat
    data = json.loads(heartbeat_file.read_text())
    assert data["component"] == "outcome_tracker"
    assert data["status"] == "healthy"
    assert "timestamp_unix" in data
    assert "evaluated" in data
    assert "errors" in data


def test_graceful_shutdown_on_signal(tmp_path):
    """Daemon should exit cleanly when SIGINT is received."""
    fake_time = FakeTime()
    heartbeat_file = tmp_path / "outcome_tracker.heartbeat"
    run_count = 0

    def mock_run(**kwargs):
        nonlocal run_count
        run_count += 1
        return {"evaluated": 0, "skipped": 0, "errors": 0}

    def trigger_sigint():
        time.sleep(0.05)
        os.kill(os.getpid(), signal.SIGINT)

    shutdown_thread = threading.Thread(target=trigger_sigint, daemon=True)
    shutdown_thread.start()

    with patch("core.outcome_tracker.run", side_effect=mock_run):
        run_daemon(
            interval=60,
            heartbeat_path=str(heartbeat_file),
            _time_module=fake_time,
        )

    # Should have run at least once and exited without error
    assert run_count >= 1


def test_interval_respected(tmp_path):
    """Daemon should sleep for the configured interval between cycles."""
    fake_time = FakeTime()
    heartbeat_file = tmp_path / "outcome_tracker.heartbeat"
    interval = 120

    def mock_run(**kwargs):
        return {"evaluated": 0, "skipped": 0, "errors": 0}

    with patch("core.outcome_tracker.run", side_effect=mock_run):
        run_daemon(
            interval=interval,
            heartbeat_path=str(heartbeat_file),
            max_cycles=3,
            _time_module=fake_time,
        )

    # 3 cycles → 2 sleep calls (no sleep after final cycle)
    assert len(fake_time.sleep_calls) == 2
    for sleep_dur in fake_time.sleep_calls:
        assert sleep_dur == interval


def test_single_run_mode_unchanged():
    """--once mode (no --daemon) should still work as before."""
    parser = build_parser()
    # Default args should parse without --daemon
    args = parser.parse_args([])
    assert not args.daemon
    assert args.once is True
    assert args.interval == 300

    # Explicit --daemon flag
    args = parser.parse_args(["--daemon"])
    assert args.daemon is True
    assert args.interval == 300

    # Custom interval with --daemon
    args = parser.parse_args(["--daemon", "--interval", "60"])
    assert args.daemon is True
    assert args.interval == 60
