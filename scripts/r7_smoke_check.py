#!/usr/bin/env python3
"""Read-only deployment gate for the 14-day Rainbow R7 shadow phase.

The command intentionally uses only the Python standard library.  It can run
on Hermes without adding a package or talking to anything except Rainbow's
read-only HTTP endpoints.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


class SmokeCheckError(RuntimeError):
    """Raised when an HTTP response or saved snapshot cannot be used."""


@dataclass(frozen=True)
class SmokeResult:
    """Machine-readable result for one R7 smoke-check cycle."""

    errors: list[str]
    warnings: list[str]
    snapshot: dict[str, Any]

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": self.errors,
            "warnings": self.warnings,
            "snapshot": self.snapshot,
        }


def _as_non_negative_int(value: Any, field: str, errors: list[str]) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        errors.append(f"metrics.{field} must be a non-negative integer")
        return None
    return value


def _as_probability(value: Any, field: str, errors: list[str]) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.0 <= value <= 1.0:
        errors.append(f"metrics.{field} must be a number between 0.0 and 1.0")


def _parse_utc_timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("created_at is missing")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("created_at must include a timezone")
    return parsed.astimezone(timezone.utc)


def validate_snapshot(
    *,
    health: dict[str, Any],
    signals: list[dict[str, Any]],
    metrics: dict[str, Any],
    expected_collectors: list[str],
    previous_signals_stored_count: int | None = None,
    now: datetime | None = None,
    require_signal: bool = False,
    allow_extra_collectors: bool = False,
) -> SmokeResult:
    """Validate the read-only R7 contract returned by one endpoint cycle."""
    errors: list[str] = []
    warnings: list[str] = []
    checked_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)

    if health.get("status") != "healthy":
        errors.append(f"health status is {health.get('status')!r}, expected 'healthy'")
    if health.get("read_only") is not True:
        errors.append("health.read_only must be true")
    if health.get("collectors_fresh") is not True:
        errors.append("health.collectors_fresh must be true")

    collectors = health.get("collectors")
    if not isinstance(collectors, dict):
        errors.append("health.collectors must be an object")
        collectors = {}
    active_collectors = sorted(name for name, status in collectors.items() if status == "running")
    expected = sorted(set(expected_collectors))
    for name in expected:
        if collectors.get(name) != "running":
            errors.append(f"collector '{name}' is not running")
    if not allow_extra_collectors and active_collectors != expected:
        errors.append(
            f"active collectors are {active_collectors}, expected exactly {expected}"
        )

    stored_count = _as_non_negative_int(metrics.get("signals_stored_count"), "signals_stored_count", errors)
    active_count = _as_non_negative_int(metrics.get("collectors_active"), "collectors_active", errors)
    total_count = _as_non_negative_int(metrics.get("collectors_total"), "collectors_total", errors)
    if active_count is not None and active_count != len(active_collectors):
        errors.append("metrics.collectors_active does not match health.collectors")
    if total_count is not None and total_count != len(collectors):
        errors.append("metrics.collectors_total does not match health.collectors")

    _as_probability(metrics.get("win_rate_rolling_50"), "win_rate_rolling_50", errors)
    _as_probability(metrics.get("confidence_calibration_error"), "confidence_calibration_error", errors)
    _as_non_negative_int(metrics.get("performance_sample_size"), "performance_sample_size", errors)
    if not isinstance(metrics.get("drift_alarm_active"), bool):
        errors.append("metrics.drift_alarm_active must be a boolean")

    if (
        stored_count is not None
        and previous_signals_stored_count is not None
        and stored_count < previous_signals_stored_count
    ):
        errors.append(
            "signals_stored_count regressed "
            f"from {previous_signals_stored_count} to {stored_count}"
        )

    if not signals:
        message = "canonical endpoint returned no signals"
        if require_signal:
            errors.append(message)
        else:
            warnings.append(message)
    elif stored_count == 0:
        errors.append("canonical endpoint returned signals while signals_stored_count is zero")

    for index, signal in enumerate(signals):
        prefix = f"signal[{index}]"
        if not isinstance(signal, dict):
            errors.append(f"{prefix} is not an object")
            continue

        actionability = signal.get("actionability")
        if not isinstance(actionability, dict):
            errors.append(f"{prefix}.actionability is missing")
        else:
            if actionability.get("can_execute") is not False:
                errors.append(f"{prefix}.actionability.can_execute must be false")
            if actionability.get("dry_run_only") is not True:
                errors.append(f"{prefix}.actionability.dry_run_only must be true")

        data_quality = signal.get("data_quality")
        if not isinstance(data_quality, dict):
            errors.append(f"{prefix}.data_quality is missing")
            data_quality = {}
        if data_quality.get("status") != "ok":
            errors.append(f"{prefix} data quality status must be 'ok'")

        invalidation = signal.get("invalidation")
        max_age = invalidation.get("max_age_seconds") if isinstance(invalidation, dict) else None
        if isinstance(max_age, bool) or not isinstance(max_age, int) or max_age <= 0:
            errors.append(f"{prefix}.invalidation.max_age_seconds must be a positive integer")
            continue

        freshness = data_quality.get("freshness_seconds")
        if isinstance(freshness, bool) or not isinstance(freshness, int) or freshness < 0:
            errors.append(f"{prefix}.data_quality.freshness_seconds must be a non-negative integer")
        elif freshness > max_age:
            errors.append(f"{prefix} freshness_seconds exceeds its invalidation max age")

        try:
            created_at = _parse_utc_timestamp(signal.get("created_at"))
        except (TypeError, ValueError) as exc:
            errors.append(f"{prefix}.{exc}")
            continue
        age_seconds = (checked_at - created_at).total_seconds()
        if age_seconds < -5:
            errors.append(f"{prefix}.created_at is in the future")
        elif age_seconds > max_age:
            errors.append(f"{prefix} is older than its invalidation max age")

    snapshot = {
        "checked_at_utc": checked_at.isoformat().replace("+00:00", "Z"),
        "signals_stored_count": stored_count,
        "active_collectors": active_collectors,
        "canonical_signal_count": len(signals),
        "health_status": health.get("status"),
    }
    return SmokeResult(errors=errors, warnings=warnings, snapshot=snapshot)


def _fetch_json(url: str, timeout_seconds: float) -> Any:
    try:
        with urlopen(url, timeout=timeout_seconds) as response:  # noqa: S310 -- target is an explicit CLI argument
            if response.status != 200:
                raise SmokeCheckError(f"GET {url} returned HTTP {response.status}")
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise SmokeCheckError(f"GET {url} returned HTTP {exc.code}") from exc
    except URLError as exc:
        raise SmokeCheckError(f"GET {url} failed: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise SmokeCheckError(f"GET {url} did not return JSON") from exc


def _load_previous_count(snapshot_path: Path) -> int | None:
    if not snapshot_path.exists():
        return None
    try:
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SmokeCheckError(f"cannot read snapshot {snapshot_path}: {exc}") from exc
    count = snapshot.get("signals_stored_count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise SmokeCheckError(f"snapshot {snapshot_path} has no valid signals_stored_count")
    return count


def _save_snapshot(snapshot_path: Path, snapshot: dict[str, Any]) -> None:
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the read-only R7 Rainbow deployment contract")
    parser.add_argument("--base-url", required=True, help="Rainbow base URL, e.g. http://127.0.0.1:8000")
    parser.add_argument("--expected-collector", action="append", default=None, help="Collector expected to be running (repeatable; default: ta)")
    parser.add_argument("--allow-extra-collectors", action="store_true", help="Do not fail when additional collectors are active")
    parser.add_argument("--require-signal", action="store_true", help="Fail if the canonical endpoint is empty")
    parser.add_argument("--snapshot-path", type=Path, help="External JSON path used to detect a decreasing stored-signal count")
    parser.add_argument("--timeout-seconds", type=float, default=10.0, help="HTTP timeout per endpoint (default: 10)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.timeout_seconds <= 0:
        raise SystemExit("--timeout-seconds must be greater than zero")
    base_url = args.base_url.rstrip("/")
    expected_collectors = args.expected_collector or ["ta"]
    try:
        previous_count = _load_previous_count(args.snapshot_path) if args.snapshot_path else None
        health = _fetch_json(f"{base_url}/health", args.timeout_seconds)
        signals = _fetch_json(f"{base_url}/signals/canonical/latest?limit=50", args.timeout_seconds)
        metrics = _fetch_json(f"{base_url}/metrics", args.timeout_seconds)
        if not isinstance(health, dict) or not isinstance(signals, list) or not isinstance(metrics, dict):
            raise SmokeCheckError("endpoint response types must be object, list, object")
        result = validate_snapshot(
            health=health,
            signals=signals,
            metrics=metrics,
            expected_collectors=expected_collectors,
            previous_signals_stored_count=previous_count,
            require_signal=args.require_signal,
            allow_extra_collectors=args.allow_extra_collectors,
        )
        if result.ok and args.snapshot_path:
            _save_snapshot(args.snapshot_path, result.snapshot)
        print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
        return 0 if result.ok else 1
    except SmokeCheckError as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)], "warnings": [], "snapshot": {}}, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
