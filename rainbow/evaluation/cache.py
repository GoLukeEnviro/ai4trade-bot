from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from typing import Optional

from rainbow.evaluation.models import AIEvaluation


class EvaluationCache:
    def __init__(self, ttl_seconds: int = 300, max_size: int = 500) -> None:
        self._ttl = ttl_seconds
        self._max_size = max_size
        self._store: OrderedDict[str, tuple[AIEvaluation, float]] = OrderedDict()
        self._lock = asyncio.Lock()

    def _make_key(self, asset: str, direction: str) -> str:
        return f"{asset}:{direction}"

    async def get(self, asset: str, direction: str) -> Optional[AIEvaluation]:
        key = self._make_key(asset, direction)
        async with self._lock:
            if key not in self._store:
                return None
            evaluation, stored_at = self._store[key]
            if time.monotonic() - stored_at >= self._ttl:
                del self._store[key]
                return None
            self._store.move_to_end(key)
            return evaluation

    async def set(self, asset: str, direction: str, evaluation: AIEvaluation) -> None:
        key = self._make_key(asset, direction)
        async with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
            self._store[key] = (evaluation, time.monotonic())
            while len(self._store) > self._max_size:
                self._store.popitem(last=False)
