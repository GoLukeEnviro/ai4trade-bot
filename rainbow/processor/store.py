from __future__ import annotations

import json
from pathlib import Path

import aiosqlite

from rainbow.models.signal import CryptoSignal


class SignalStore:
    def __init__(self, db_path: str = "rainbow/storage/signals.db"):
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def start(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._db_path)
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._create_tables()

    async def _create_tables(self) -> None:
        await self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS signals (
                signal_id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                source TEXT NOT NULL,
                asset TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                direction TEXT,
                strength REAL,
                confidence REAL,
                value REAL,
                raw_data TEXT,
                metadata TEXT,
                rainbow_score REAL,
                ai_evaluation TEXT
            )
        """)
        await self._conn.commit()

    async def save(self, signal: CryptoSignal) -> None:
        ai_eval_json = json.dumps(signal.ai_evaluation.model_dump()) if signal.ai_evaluation else None
        await self._conn.execute(
            """INSERT OR IGNORE INTO signals
               (signal_id, timestamp, source, asset, signal_type, direction,
                strength, confidence, value, raw_data, metadata, rainbow_score, ai_evaluation)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                signal.signal_id,
                signal.timestamp.isoformat(),
                signal.source,
                signal.asset,
                signal.signal_type.value,
                signal.direction.value if signal.direction else None,
                signal.strength,
                signal.confidence,
                signal.value,
                json.dumps(signal.raw_data) if signal.raw_data else None,
                json.dumps(signal.metadata) if signal.metadata else None,
                signal.rainbow_score,
                ai_eval_json,
            ),
        )
        await self._conn.commit()

    async def get_latest(
        self,
        asset: str | None = None,
        source: str | None = None,
        signal_type: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        query = "SELECT * FROM signals WHERE 1=1"
        params: list[str | int] = []
        if asset:
            query += " AND asset = ?"
            params.append(asset)
        if source:
            query += " AND source = ?"
            params.append(source)
        if signal_type:
            query += " AND signal_type = ?"
            params.append(signal_type)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        cursor = await self._conn.execute(query, params)
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in await cursor.fetchall()]

    async def get_by_id(self, signal_id: str) -> dict | None:
        cursor = await self._conn.execute("SELECT * FROM signals WHERE signal_id = ?", (signal_id,))
        columns = [desc[0] for desc in cursor.description]
        row = await cursor.fetchone()
        return dict(zip(columns, row)) if row else None

    async def stop(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None
