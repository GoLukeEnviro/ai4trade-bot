"""Canonical signal registry — SQLite-backed lifecycle store."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from core.signals.envelope import CanonicalSignalEnvelope, SignalClass

log = logging.getLogger(__name__)


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
    source        TEXT NOT NULL DEFAULT '',
    updated_at    TEXT NOT NULL DEFAULT ''
);
"""

_CREATE_INDEX_SQL = """\
CREATE INDEX IF NOT EXISTS idx_canonical_signals_asset ON canonical_signals(asset);
CREATE INDEX IF NOT EXISTS idx_canonical_signals_class ON canonical_signals(signal_class);
CREATE INDEX IF NOT EXISTS idx_canonical_signals_lifecycle ON canonical_signals(lifecycle);
CREATE INDEX IF NOT EXISTS idx_signals_asset_time ON canonical_signals(asset, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_signals_source ON canonical_signals(source, created_at DESC);
"""


class CanonicalSignalRegistry:
    """SQLite-backed registry for canonical signal envelopes.

    Parameters
    ----------
    db_path : str
        Path to the SQLite database file. Parent directories are created
        automatically.
    """

    def __init__(self, db_path: str = "rainbow/storage/canonical_signals.db") -> None:
        self._db_path = db_path
        self._lock = threading.Lock()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute("PRAGMA cache_size=-64000")
            self._conn.execute("PRAGMA temp_store=MEMORY")
            self._conn.execute(_CREATE_TABLE_SQL)
            if not self._column_exists("source"):
                self._conn.execute(
                    "ALTER TABLE canonical_signals ADD COLUMN source TEXT NOT NULL DEFAULT ''"
                )
            for idx_sql in _CREATE_INDEX_SQL.strip().split(";"):
                idx_sql = idx_sql.strip()
                if idx_sql:
                    self._conn.execute(idx_sql)
            self._conn.commit()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _column_exists(self, column: str) -> bool:
        rows = self._conn.execute("PRAGMA table_info(canonical_signals)").fetchall()
        return any(row[1] == column for row in rows)

    def append(self, envelope: CanonicalSignalEnvelope) -> str:
        """Store a new signal envelope. Returns the signal id."""
        payload = envelope.model_dump(mode="json")
        payload["signal_class"] = payload.pop("class", payload.get("signal_class"))
        envelope_json = json.dumps(payload, default=str)
        now = payload.get("created_at", "")
        with self._lock:
            self._conn.execute(
                "INSERT INTO canonical_signals "
                "(id, envelope_json, lifecycle, created_at, asset, signal_class, source, updated_at) "
                "VALUES (?, ?, 'emitted', ?, ?, ?, ?, ?)",
                (
                    envelope.id,
                    envelope_json,
                    str(now),
                    envelope.asset,
                    envelope.signal_class.value,
                    envelope.source,
                    str(now),
                ),
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
        query = "SELECT envelope_json, lifecycle, reason FROM canonical_signals WHERE 1=1"
        params: list[Any] = []
        if asset is not None:
            query += " AND asset = ?"
            params.append(asset)
        if signal_class is not None:
            query += " AND signal_class = ?"
            params.append(signal_class.value)
        query += " ORDER BY rowid DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def count(self) -> int:
        """Return the total number of canonical signals in the registry."""
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) FROM canonical_signals").fetchone()
        return int(row[0]) if row else 0

    def get_signals_in_range(
        self,
        asset: str,
        since: "datetime",
        until: "datetime",
    ) -> list[CanonicalSignalEnvelope]:
        """Return canonical envelopes for an asset within a created_at range."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT envelope_json FROM canonical_signals "
                "WHERE asset = ? AND created_at >= ? AND created_at <= ? "
                "ORDER BY created_at ASC",
                (asset, since.isoformat(), until.isoformat()),
            ).fetchall()
        return [CanonicalSignalEnvelope.model_validate_json(row[0]) for row in rows]

    def get_signals_before(self, cutoff: "datetime") -> list[CanonicalSignalEnvelope]:
        """Return canonical envelopes created before cutoff."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT envelope_json FROM canonical_signals WHERE created_at < ? ORDER BY created_at ASC",
                (cutoff.isoformat(),),
            ).fetchall()
        return [CanonicalSignalEnvelope.model_validate_json(row[0]) for row in rows]

    def delete_signals_before(self, cutoff: "datetime") -> int:
        """Delete canonical signals created before cutoff and return the row count."""
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM canonical_signals WHERE created_at < ?",
                (cutoff.isoformat(),),
            )
            self._conn.commit()
            return cur.rowcount

    def query_active(
        self,
        asset: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return signals that have NOT been expired or invalidated."""
        query = (
            "SELECT envelope_json, lifecycle, reason FROM canonical_signals"
            " WHERE lifecycle NOT IN ('expired', 'invalidated')"
        )
        params: list[Any] = []
        if asset is not None:
            query += " AND asset = ?"
            params.append(asset)
        query += " ORDER BY rowid DESC"
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
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
        query = (
            "SELECT envelope_json, lifecycle, reason FROM canonical_signals"
            " WHERE lifecycle = 'emitted' AND created_at <= ?"
        )
        params: list[Any] = [str(cutoff)]
        if signal_class is not None:
            query += " AND signal_class = ?"
            params.append(signal_class.value)
        query += " ORDER BY created_at ASC LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
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

    def get_latest_canonical(self, asset: str) -> CanonicalSignalEnvelope | None:
        """Return the most recent CanonicalSignalEnvelope for *asset*, or None.

        This is the preferred read path for consumers that need a fully
        validated envelope object (e.g. FreqtradeBridge).
        """
        rows = self.query_latest(asset=asset, limit=1)
        if not rows:
            return None
        try:
            return CanonicalSignalEnvelope.model_validate(rows[0])
        except Exception as exc:
            log.warning("get_latest_canonical: envelope validation failed for %s: %s", asset, exc)
            return None

    def close(self) -> None:
        with self._lock:
            self._conn.close()
