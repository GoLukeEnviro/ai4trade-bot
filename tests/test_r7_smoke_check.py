"""Contract tests for the R7 read-only deployment gate."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from scripts.r7_smoke_check import validate_snapshot


NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)


def _health() -> dict:
    return {
        "status": "healthy",
        "read_only": True,
        "collectors": {"ta": "running"},
        "collectors_fresh": True,
    }


def _metrics(count: int = 12) -> dict:
    return {
        "signals_stored_count": count,
        "collectors_active": 1,
        "collectors_total": 1,
        "win_rate_rolling_50": 0.0,
        "confidence_calibration_error": 0.0,
        "drift_alarm_active": False,
        "performance_sample_size": 0,
        "derivatives_last_run_utc": None,
        "funding_rate_btc_current": None,
    }


def _signal(**overrides: object) -> dict:
    signal = {
        "created_at": (NOW - timedelta(seconds=30)).isoformat(),
        "data_quality": {"status": "ok", "freshness_seconds": 30},
        "actionability": {"can_execute": False, "dry_run_only": True},
        "invalidation": {"max_age_seconds": 60},
    }
    signal.update(overrides)
    return signal


def test_accepts_fresh_safe_ta_baseline_and_emits_snapshot() -> None:
    result = validate_snapshot(
        health=_health(),
        signals=[_signal()],
        metrics=_metrics(),
        expected_collectors=["ta"],
        now=NOW,
        require_signal=True,
    )

    assert result.ok
    assert result.errors == []
    assert result.snapshot["signals_stored_count"] == 12
    assert result.snapshot["active_collectors"] == ["ta"]


def test_rejects_stale_or_unsafe_envelopes() -> None:
    result = validate_snapshot(
        health=_health(),
        signals=[
            _signal(
                created_at=(NOW - timedelta(seconds=61)).isoformat(),
                data_quality={"status": "stale", "freshness_seconds": 61},
                actionability={"can_execute": True, "dry_run_only": False},
            )
        ],
        metrics=_metrics(),
        expected_collectors=["ta"],
        now=NOW,
        require_signal=True,
    )

    assert not result.ok
    assert any("data quality" in error for error in result.errors)
    assert any("can_execute" in error for error in result.errors)
    assert any("dry_run_only" in error for error in result.errors)
    assert any("older than its invalidation" in error for error in result.errors)


def test_rejects_metrics_regression_between_smoke_cycles() -> None:
    result = validate_snapshot(
        health=_health(),
        signals=[_signal()],
        metrics=_metrics(count=11),
        expected_collectors=["ta"],
        previous_signals_stored_count=12,
        now=NOW,
    )

    assert not result.ok
    assert any("regressed" in error for error in result.errors)
