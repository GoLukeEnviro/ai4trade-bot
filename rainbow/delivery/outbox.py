"""Durable SQLite outbox for optional AI4Trade delivery."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import aiosqlite

from rainbow.delivery.models import AI4TradePayload


@dataclass(frozen=True)
class OutboxEntry:
    payload: AI4TradePayload
    attempts: int


class DeliveryOutbox:
    def __init__(self, path: str) -> None:
        self._path = path
        self._connection: aiosqlite.Connection | None = None

    async def start(self) -> None:
        if self._connection is not None:
            return
        if self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._connection = await aiosqlite.connect(self._path)
        await self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ai4trade_outbox (
                fingerprint TEXT PRIMARY KEY,
                signal_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT
            )
            """
        )
        await self._connection.commit()

    async def enqueue(self, payload: AI4TradePayload | None, *, status: str) -> bool:
        if payload is None:
            return False
        connection = self._require_connection()
        cursor = await connection.execute(
            """
            INSERT OR IGNORE INTO ai4trade_outbox
              (fingerprint, signal_id, payload_json, status)
            VALUES (?, ?, ?, ?)
            """,
            (payload.fingerprint, payload.signal_id, json.dumps(payload.as_request_json()), status),
        )
        await connection.commit()
        return cursor.rowcount == 1

    async def pending(self) -> list[OutboxEntry]:
        connection = self._require_connection()
        cursor = await connection.execute(
            "SELECT fingerprint, signal_id, payload_json, attempts "
            "FROM ai4trade_outbox WHERE status IN ('pending', 'retrying')"
        )
        entries: list[OutboxEntry] = []
        for fingerprint, signal_id, payload_json, attempts in await cursor.fetchall():
            payload = json.loads(payload_json)
            entries.append(
                OutboxEntry(
                    payload=AI4TradePayload(
                        fingerprint=fingerprint,
                        signal_id=signal_id,
                        market=str(payload["market"]),
                        action=str(payload["action"]),
                        symbol=str(payload["symbol"]),
                        price=float(payload["price"]),
                        quantity=float(payload["quantity"]),
                    ),
                    attempts=int(attempts),
                )
            )
        return entries

    async def mark_sent(self, fingerprint: str) -> None:
        await self._set_status(fingerprint, "sent")

    async def mark_retrying(self, fingerprint: str, error: str) -> int:
        connection = self._require_connection()
        await connection.execute(
            "UPDATE ai4trade_outbox SET status = 'retrying', attempts = attempts + 1, "
            "last_error = ? WHERE fingerprint = ?",
            (error[:500], fingerprint),
        )
        await connection.commit()
        cursor = await connection.execute("SELECT attempts FROM ai4trade_outbox WHERE fingerprint = ?", (fingerprint,))
        row = await cursor.fetchone()
        return int(row[0]) if row else 0

    async def mark_dead_letter(self, fingerprint: str, error: str) -> None:
        await self._set_status(fingerprint, "dead_letter", error)

    async def count_by_status(self, status: str) -> int:
        connection = self._require_connection()
        cursor = await connection.execute("SELECT COUNT(*) FROM ai4trade_outbox WHERE status = ?", (status,))
        row = await cursor.fetchone()
        return int(row[0])

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            self._connection = None

    async def _set_status(self, fingerprint: str, status: str, error: str | None = None) -> None:
        connection = self._require_connection()
        await connection.execute(
            "UPDATE ai4trade_outbox SET status = ?, last_error = ? WHERE fingerprint = ?",
            (status, error[:500] if error else None, fingerprint),
        )
        await connection.commit()

    def _require_connection(self) -> aiosqlite.Connection:
        if self._connection is None:
            raise RuntimeError("DeliveryOutbox.start() must be called before use")
        return self._connection
