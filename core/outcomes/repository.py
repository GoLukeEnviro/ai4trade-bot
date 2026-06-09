"""Outcome persistence — SQLite-backed storage for signal outcomes."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from core.outcomes.model import OutcomeLabel, SignalOutcome

log = logging.getLogger(__name__)

_CREATE_TABLE_SQL = """\
CREATE TABLE IF NOT EXISTS signal_outcomes (
    signal_id               TEXT PRIMARY KEY,
    asset                   TEXT NOT NULL,
    direction               TEXT NOT NULL,
    signal_class            TEXT NOT NULL,
    source                  TEXT NOT NULL DEFAULT '',
    emitted_at              TEXT NOT NULL,
    evaluated_at            TEXT NOT NULL,
    evaluation_window_seconds INTEGER NOT NULL DEFAULT 3600,
    entry_price             REAL,
    outcome_price           REAL,
    price_change_pct        REAL,
    expected_direction      TEXT NOT NULL DEFAULT '',
    outcome_label           TEXT NOT NULL DEFAULT 'unknown',
    outcome_score           REAL NOT NULL DEFAULT 0.0,
    reason                  TEXT NOT NULL DEFAULT '',
    confidence_at_signal    REAL,
    extra_json              TEXT NOT NULL DEFAULT '{}',
    updated_at              TEXT NOT NULL DEFAULT ''
);
"""

_CREATE_INDEX_SQL = """\
CREATE INDEX IF NOT EXISTS idx_signal_outcomes_asset ON signal_outcomes(asset);
CREATE INDEX IF NOT EXISTS idx_signal_outcomes_label ON signal_outcomes(outcome_label);
CREATE INDEX IF NOT EXISTS idx_signal_outcomes_emitted ON signal_outcomes(emitted_at);
"""


class OutcomeRepository:
    """SQLite-backed repository for signal outcomes.

    Parameters
    ----------
    db_path : str
        Path to the SQLite database file. Uses a dedicated database
        (``storage/outcomes.db``) to avoid touching the canonical registry.
    """

    def __init__(self, db_path: str = "storage/outcomes.db") -> None:
        self._db_path = db_path
        self._lock = threading.Lock()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute(_CREATE_TABLE_SQL)
            for idx_sql in _CREATE_INDEX_SQL.strip().split(";"):
                idx_sql = idx_sql.strip()
                if idx_sql:
                    self._conn.execute(idx_sql)
            self._conn.commit()

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def insert(self, outcome: SignalOutcome) -> None:
        """Insert a new outcome. Raises on duplicate signal_id."""
        with self._lock:
            self._conn.execute(
                """INSERT INTO signal_outcomes
                   (signal_id, asset, direction, signal_class, source, emitted_at,
                    evaluated_at, evaluation_window_seconds, entry_price, outcome_price,
                    price_change_pct, expected_direction, outcome_label, outcome_score,
                    reason, confidence_at_signal, extra_json, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    outcome.signal_id,
                    outcome.asset,
                    outcome.direction,
                    outcome.signal_class,
                    outcome.source,
                    _dt_to_str(outcome.emitted_at),
                    _dt_to_str(outcome.evaluated_at),
                    outcome.evaluation_window_seconds,
                    outcome.entry_price,
                    outcome.outcome_price,
                    outcome.price_change_pct,
                    outcome.expected_direction,
                    outcome.outcome_label.value,
                    outcome.outcome_score,
                    outcome.reason,
                    outcome.confidence_at_signal,
                    json.dumps(outcome.extra, default=str),
                    _utcnow_str(),
                ),
            )
            self._conn.commit()

    def upsert(self, outcome: SignalOutcome) -> None:
        """Insert or update an outcome (idempotent)."""
        with self._lock:
            self._conn.execute(
                """INSERT INTO signal_outcomes
                   (signal_id, asset, direction, signal_class, source, emitted_at,
                    evaluated_at, evaluation_window_seconds, entry_price, outcome_price,
                    price_change_pct, expected_direction, outcome_label, outcome_score,
                    reason, confidence_at_signal, extra_json, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(signal_id) DO UPDATE SET
                    evaluated_at=excluded.evaluated_at,
                    evaluation_window_seconds=excluded.evaluation_window_seconds,
                    entry_price=excluded.entry_price,
                    outcome_price=excluded.outcome_price,
                    price_change_pct=excluded.price_change_pct,
                    outcome_label=excluded.outcome_label,
                    outcome_score=excluded.outcome_score,
                    reason=excluded.reason,
                    extra_json=excluded.extra_json,
                    updated_at=excluded.updated_at""",
                (
                    outcome.signal_id,
                    outcome.asset,
                    outcome.direction,
                    outcome.signal_class,
                    outcome.source,
                    _dt_to_str(outcome.emitted_at),
                    _dt_to_str(outcome.evaluated_at),
                    outcome.evaluation_window_seconds,
                    outcome.entry_price,
                    outcome.outcome_price,
                    outcome.price_change_pct,
                    outcome.expected_direction,
                    outcome.outcome_label.value,
                    outcome.outcome_score,
                    outcome.reason,
                    outcome.confidence_at_signal,
                    json.dumps(outcome.extra, default=str),
                    _utcnow_str(),
                ),
            )
            self._conn.commit()

    def has_outcome(self, signal_id: str) -> bool:
        """Check if an outcome already exists for this signal."""
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM signal_outcomes WHERE signal_id = ?",
                (signal_id,),
            ).fetchone()
        return row is not None

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get_by_signal_id(self, signal_id: str) -> SignalOutcome | None:
        """Retrieve an outcome by signal_id, or None."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM signal_outcomes WHERE signal_id = ?",
                (signal_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_outcome(row)

    def query(
        self,
        asset: str | None = None,
        outcome_label: OutcomeLabel | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SignalOutcome]:
        """Query outcomes with optional filters."""
        clauses: list[str] = []
        params: list[Any] = []
        if asset is not None:
            clauses.append("asset = ?")
            params.append(asset)
        if outcome_label is not None:
            clauses.append("outcome_label = ?")
            params.append(outcome_label.value)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._lock:
            rows = self._conn.execute(
                f"SELECT * FROM signal_outcomes {where} ORDER BY emitted_at DESC LIMIT ? OFFSET ?",
                (*params, limit, offset),
            ).fetchall()
        return [self._row_to_outcome(r) for r in rows]

    def count(self, outcome_label: OutcomeLabel | None = None) -> int:
        """Count outcomes, optionally filtered by label."""
        with self._lock:
            if outcome_label is not None:
                row = self._conn.execute(
                    "SELECT COUNT(*) FROM signal_outcomes WHERE outcome_label = ?",
                    (outcome_label.value,),
                ).fetchone()
            else:
                row = self._conn.execute("SELECT COUNT(*) FROM signal_outcomes").fetchone()
        return row[0] if row else 0

    def export_all(self) -> list[dict[str, Any]]:
        """Export all outcomes as plain dicts (training-ready)."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM signal_outcomes ORDER BY emitted_at"
            ).fetchall()
            cols = [d[0] for d in self._conn.execute("SELECT * FROM signal_outcomes LIMIT 0").description]
        return [dict(zip(cols, r)) for r in rows]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_outcome(row: tuple) -> SignalOutcome:
        cols = [
            "signal_id", "asset", "direction", "signal_class", "source",
            "emitted_at", "evaluated_at", "evaluation_window_seconds",
            "entry_price", "outcome_price", "price_change_pct",
            "expected_direction", "outcome_label", "outcome_score",
            "reason", "confidence_at_signal", "extra_json", "updated_at",
        ]
        d = dict(zip(cols, row))
        extra = d.pop("extra_json", "{}")
        d.pop("updated_at", None)
        d["emitted_at"] = _parse_dt(d["emitted_at"])
        d["evaluated_at"] = _parse_dt(d["evaluated_at"])
        try:
            d["extra"] = json.loads(extra) if isinstance(extra, str) else {}
        except (json.JSONDecodeError, TypeError):
            d["extra"] = {}
        return SignalOutcome(**d)

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def _utcnow_str() -> str:
    from datetime import UTC
    return str(datetime.now(UTC))


def _dt_to_str(dt: datetime) -> str:
    return str(dt)


def _parse_dt(val: str | datetime) -> datetime:
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(val)
    except (ValueError, TypeError):
        from datetime import UTC
        return datetime.now(UTC)
