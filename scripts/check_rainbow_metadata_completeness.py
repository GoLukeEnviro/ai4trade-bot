"""Fixture-based Rainbow metadata completeness checker (Issue #58)."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "docs/integration/fixtures/rainbow-signals"

REQUIRED_TOP_LEVEL = (
    "event_type",
    "schema_version",
    "source_system",
    "source_id",
    "strategy_id",
    "symbol",
    "timestamp_utc",
    "direction",
    "confidence",
    "metadata",
    "redaction_status",
)

OPTIONAL_TOP_LEVEL = (
    "model_id",
    "timeframe",
    "emitted_at_utc",
    "signal_strength",
    "regime_hint",
)

OPTIONAL_METADATA_KEYS = ("reason_codes", "data_quality", "features", "raw_refs")


@dataclass
class FixtureReport:
    path: str
    verdict: str  # GREEN, YELLOW, RED
    missing_required: list[str] = field(default_factory=list)
    missing_optional: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _check_fixture(path: Path) -> FixtureReport:
    name = path.name
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return FixtureReport(name, "RED", notes=[f"unreadable: {exc}"])

    if not isinstance(data, dict):
        return FixtureReport(name, "RED", notes=["root must be object"])

    missing_required = [k for k in REQUIRED_TOP_LEVEL if k not in data]
    if missing_required:
        return FixtureReport(name, "RED", missing_required=missing_required)

    missing_optional = [k for k in OPTIONAL_TOP_LEVEL if k not in data]
    metadata = data.get("metadata")
    event_type = data.get("event_type")
    if isinstance(metadata, dict) and event_type == "signal":
        missing_optional.extend(
            f"metadata.{k}" for k in OPTIONAL_METADATA_KEYS if k not in metadata
        )
    elif not isinstance(metadata, dict):
        missing_optional.append("metadata (object)")

    notes: list[str] = []
    if data.get("event_type") == "signal":
        dq = (metadata or {}).get("data_quality", {})
        if isinstance(dq, dict) and dq.get("status") == "stale":
            notes.append("semantically stale signal")

    verdict = "YELLOW" if missing_optional or notes else "GREEN"
    return FixtureReport(name, verdict, missing_optional=missing_optional, notes=notes)


def run(fixtures_dir: Path = FIXTURES_DIR) -> list[FixtureReport]:
    reports: list[FixtureReport] = []
    for path in sorted(fixtures_dir.glob("*.json")):
        reports.append(_check_fixture(path))
    return reports


def format_markdown(reports: list[FixtureReport]) -> str:
    lines = ["# Rainbow Metadata Completeness Report", ""]
    for r in reports:
        lines.append(f"## {r.path}")
        lines.append(f"- **Verdict:** {r.verdict}")
        if r.missing_required:
            lines.append(f"- **Missing required:** {', '.join(r.missing_required)}")
        if r.missing_optional:
            lines.append(f"- **Missing optional:** {', '.join(r.missing_optional)}")
        if r.notes:
            lines.append(f"- **Notes:** {'; '.join(r.notes)}")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, default=FIXTURES_DIR)
    parser.add_argument("--format", choices=("text", "json", "markdown"), default="text")
    parser.add_argument("--fail-on", choices=("red", "yellow", "never"), default="red")
    args = parser.parse_args(argv)

    reports = run(args.fixtures)
    if args.format == "json":
        payload = [
            {
                "path": r.path,
                "verdict": r.verdict,
                "missing_required": r.missing_required,
                "missing_optional": r.missing_optional,
                "notes": r.notes,
            }
            for r in reports
        ]
        print(json.dumps(payload, indent=2))
    elif args.format == "markdown":
        print(format_markdown(reports))
    else:
        for r in reports:
            print(f"{r.path}: {r.verdict}")

    if args.fail_on == "never":
        return 0
    if args.fail_on == "red" and any(r.verdict == "RED" for r in reports):
        return 1
    if args.fail_on == "yellow" and any(r.verdict in ("RED", "YELLOW") for r in reports):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
