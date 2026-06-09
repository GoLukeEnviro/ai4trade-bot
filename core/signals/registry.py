"""Canonical signal registry — SQLite-backed lifecycle store."""

from __future__ import annotations

import json
import sqlite3
import threading
from enum import StrEnum
from pathlib import Path
from typing import Any

from core.signals.envelope import CanonicalSignalEnvelope, SignalClass


class SignalLifecycle(StrEnum):
    """Possible lifecycle states for a signal."""

    EMITTED = "emitted"
    EXPIRED = "expired"
    INVALIDATED = "invalidated"
    RESOLVED_WIN = "resolved_win"
    RESOLVED_LOSS = "resolved_loss"


_CREATE_TABLE_SQL = """\
CREATE TABLE IF NOT EXISTS canonical_signals (
    id            TEXT PRIMARY KEY,
    envelope_json TEXT NOT NULL,
    lifecycle     TEXT NOT NULL DEFAULT 'emitted',
    reason        TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL,
    asset         TEXT NOT NULL,
    signal_class  TEXT NOT NULL,
    updated_at    TEXT NOT NULL DEFAULT ''
);
"""

_CREATE_INDEX_SQL = """\
CREATE INDEX IF NOT EXISTS idx_canonical_signals_asset ON canonical_signals(asset);
CREATE INDEX IF NOT EXISTS idx_canonical_signals_class ON canonical_signals(signal_class);
CREATE INDEX IF NOT EXISTS idx_canonical_signals_lifecycle ON canonical_signals(lifecycle);
"""


class CanonicalSignalRegistry:
    """SQLite-backed registry for canonical signal envelopes.

    Parameters
    ----------
    db_path : str
        Path to the SQLite database file. Parent directories are created
        automatically.
    """

    def __init__(self, db_path: str = "storage/canonical_signals.db") -> None:
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
    # Public API
    # ------------------------------------------------------------------

    def append(self, envelope: CanonicalSignalEnvelope) -> str:
        """Store a new signal envelope. Returns the signal id."""
        payload = envelope.model_dump(mode="json")
        payload["signal_class"] = payload.pop("class", payload.get("signal_class"))
        envelope_json = json.dumps(payload, default=str)
        now = payload.get("created_at", "")
        with self._lock:
            self._conn.execute(
                "INSERT INTO canonical_signals "
                "(id, envelope_json, lifecycle, created_at, asset, signal_class, updated_at) "
                "VALUES (?, ?, 'emitted', ?, ?, ?, ?)",
                (envelope.id, envelope_json, str(now), envelope.asset, envelope.signal_class.value, str(now)),
            )
            self._conn.commit()
        return envelope.id

    def transition(
        self,
        signal_id: str,
        lifecycle: SignalLifecycle,
        reason: str = "",
    ) -> bool:
        """Move a signal to a new lifecycle state.

        Returns True if the row was updated, False otherwise (e.g. id not found).
        """
        from datetime import UTC, datetime

        now = str(datetime.now(UTC))
        with self._lock:
            cur = self._conn.execute(
                "UPDATE canonical_signals SET lifecycle = ?, reason = ?, updated_at = ? WHERE id = ?",
                (lifecycle.value, reason, now, signal_id),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def query_latest(
        self,
        asset: str | None = None,
        signal_class: SignalClass | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return the most recent signals, optionally filtered."""
        clauses: list[str] = []
        params: list[Any] = []
        if asset is not None:
            clauses.append("asset = ?")
            params.append(asset)
        if signal_class is not None:
            clauses.append("signal_class = ?")
            params.append(signal_class.value)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._lock:
            rows = self._conn.execute(
                f"SELECT envelope_json, lifecycle, reason FROM canonical_signals {where} ORDER BY rowid DESC LIMIT ?",
                (*params, limit),
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def query_active(
        self,
        asset: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return signals that have NOT been expired or invalidated."""
        clauses = ["lifecycle NOT IN ('expired', 'invalidated')"]
        params: list[Any] = []
        if asset is not None:
            clauses.append("asset = ?")
            params.append(asset)
        where = f"WHERE {' AND '.join(clauses)}"
        with self._lock:
            rows = self._conn.execute(
                f"SELECT envelope_json, lifecycle, reason FROM canonical_signals {where} ORDER BY rowid DESC",
                (*params,),
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_signal(self, signal_id: str) -> dict[str, Any] | None:
        """Retrieve a single signal by id, or None if not found."""
        with self._lock:
            row = self._conn.execute(
                "SELECT envelope_json, lifecycle, reason FROM canonical_signals WHERE id = ?",
                (signal_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    def query_open(
        self,
        min_age_seconds: int = 3600,
        signal_class: SignalClass | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return signals that are still 'emitted' and older than *min_age_seconds*.

        Useful for the outcome tracker to find signals that are ready for evaluation.
        """
        from datetime import UTC, datetime, timedelta

        cutoff = datetime.now(UTC) - timedelta(seconds=min_age_seconds)
        clauses = [
            "lifecycle = 'emitted'",
            "created_at <= ?",
        ]
        params: list[Any] = [str(cutoff)]
        if signal_class is not None:
            clauses.append("signal_class = ?")
            params.append(signal_class.value)
        where = f"WHERE {' AND '.join(clauses)}"
        with self._lock:
            sql = (
                f"SELECT envelope_json, lifecycle, reason "
                f"FROM canonical_signals {where} "
                f"ORDER BY created_at ASC LIMIT ?"
            )
            rows = self._conn.execute(sql, (*params, limit)).fetchall()
        return [self._row_to_dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_dict(row: tuple) -> dict[str, Any]:
        envelope_json, lifecycle, reason = row
        data: dict[str, Any] = json.loads(envelope_json)
        data["lifecycle"] = lifecycle
        data["transition_reason"] = reason
        return data

    def cleanup_expired(self, max_age_hours: int = 24) -> int:
        """Delete signals older than max_age_hours. Returns count of deleted rows."""
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM canonical_signals WHERE created_at < datetime('now', ?)",
                (f"-{max_age_hours} hours",),
            )
            self._conn.commit()
            return cur.rowcount

    def vacuum(self) -> None:
        """Run VACUUM on the SQLite database to reclaim space."""
        with self._lock:
            self._conn.execute("VACUUM")

    def close(self) -> None:
        with self._lock:
            self._conn.close()
