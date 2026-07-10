"""Passive AI4Trade heartbeat and task-message handling for the worker."""

from __future__ import annotations

import asyncio
import logging

log = logging.getLogger(__name__)


class AI4TradeTaskHandler:
    def __init__(self, queue: asyncio.Queue[list[dict[str, object]]]) -> None:
        self._queue = queue

    async def process_pending(self) -> int:
        processed = 0
        while not self._queue.empty():
            for message in await self._queue.get():
                if isinstance(message, dict):
                    log.info("AI4Trade task received: %s", message.get("type", "unknown"))
                    processed += 1
        return processed


class AI4TradeHeartbeat:
    def __init__(self, client, queue: asyncio.Queue[list[dict[str, object]]]) -> None:
        self._client = client
        self._queue = queue

    async def poll_once(self) -> None:
        response = await self._client.heartbeat()
        messages = response.get("messages", [])
        if isinstance(messages, list):
            typed_messages = [message for message in messages if isinstance(message, dict)]
            if typed_messages:
                await self._queue.put(typed_messages)
