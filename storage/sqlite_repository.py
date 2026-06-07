from __future__ import annotations

import json
import logging
import sqlite3
import threading

from core.signal_model import Signal
from storage.repository import SignalRepository

log = logging.getLogger(__name__)


class SqliteSignalRepository(SignalRepository):
    def __init__(self, db_path: str = "storage/bot.db") -> None:
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._create_tables()

    def _create_tables(self) -> None:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pair TEXT NOT NULL,
                    action TEXT NOT NULL,
                    confidence INTEGER,
                    price REAL,
                    quantity REAL,
                    mode TEXT DEFAULT 'dry_run',
                    timestamp REAL,
                    trace_id TEXT DEFAULT '',
                    correlation_id TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS app_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT DEFAULT (datetime('now'))
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    details_json TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS signal_outcomes (
                    signal_id TEXT PRIMARY KEY,
                    pair TEXT NOT NULL,
                    action TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    exit_price REAL,
                    outcome INTEGER,
                    evaluated_at TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)
            self._conn.commit()

    def save_signal(self, signal: Signal, trace_id: str = "", correlation_id: str = "") -> int:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """INSERT INTO signals (pair, action, confidence, price,
                   quantity, mode, timestamp, trace_id, correlation_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (signal.pair, signal.action, signal.confidence, signal.price,
                 signal.quantity, signal.mode, signal.timestamp, trace_id, correlation_id),
            )
            self._conn.commit()
            return cur.lastrowid

    def get_recent_signals(self, pair: str | None = None, limit: int = 50) -> list[dict]:
        with self._lock:
            cur = self._conn.cursor()
            if pair is not None:
                cur.execute(
                    "SELECT * FROM signals WHERE pair = ? ORDER BY created_at DESC LIMIT ?",
                    (pair, limit),
                )
            else:
                cur.execute(
                    "SELECT * FROM signals ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                )
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]

    def set_state(self, key: str, value: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO app_state (key, value, updated_at) VALUES (?, ?, datetime('now'))",
                (key, value),
            )
            self._conn.commit()

    def get_state(self, key: str, default: str = "") -> str:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("SELECT value FROM app_state WHERE key = ?", (key,))
            row = cur.fetchone()
            return row[0] if row else default

    def log_audit(self, event_type: str, details: dict | None = None) -> int:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "INSERT INTO audit_log (event_type, details_json) VALUES (?, ?)",
                (event_type, json.dumps(details) if details else None),
            )
            self._conn.commit()
            return cur.lastrowid

    def log_signal_with_id(self, signal: Signal) -> str:
        """Log a signal and return a UUID for outcome tracking."""
        import uuid

        signal_id = str(uuid.uuid4())
        with self._lock:
            self._conn.execute(
                """INSERT INTO signal_outcomes (signal_id, pair, action, entry_price)
                   VALUES (?, ?, ?, ?)""",
                (signal_id, signal.pair, signal.action, signal.price),
            )
            self._conn.commit()
        return signal_id

    def update_outcome(self, signal_id: str, exit_price: float, outcome: int) -> None:
        """Update a signal's outcome after evaluation window expires."""
        with self._lock:
            self._conn.execute(
                """UPDATE signal_outcomes
                   SET exit_price = ?, outcome = ?, evaluated_at = datetime('now')
                   WHERE signal_id = ?""",
                (exit_price, outcome, signal_id),
            )
            self._conn.commit()

    def get_pending_outcomes(self, max_age_hours: float = 4.0) -> list[dict]:
        """Get signal outcomes that haven't been evaluated yet and are older than max_age_hours."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """SELECT signal_id, pair, action, entry_price, created_at
                   FROM signal_outcomes
                   WHERE outcome IS NULL
                     AND created_at <= datetime('now', ?)""",
                (f"-{max_age_hours} hours",),
            )
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]

    def get_outcomes_for_training(self, pair: str | None = None) -> list[dict]:
        """Get evaluated outcomes for XGBoost training."""
        with self._lock:
            cur = self._conn.cursor()
            if pair is not None:
                cur.execute(
                    "SELECT * FROM signal_outcomes WHERE outcome IS NOT NULL AND pair = ?",
                    (pair,),
                )
            else:
                cur.execute("SELECT * FROM signal_outcomes WHERE outcome IS NOT NULL")
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]

    def close(self) -> None:
        with self._lock:
            self._conn.close()
