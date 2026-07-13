"""Resilience tests for the collector loop."""

import asyncio
from unittest.mock import MagicMock

from rainbow.collectors.base import BaseCollector
from rainbow.distribution import api as api_module
from rainbow.main import _run_collector_loop
from rainbow.processor.scorer import RainbowScorer


class RecoveringCollector(BaseCollector):
    def __init__(self) -> None:
        self.attempts = 0
        self.failed = asyncio.Event()
        self.recovered = asyncio.Event()

    @property
    def name(self) -> str:
        return "recovering"

    async def collect(self) -> list:
        self.attempts += 1
        if self.attempts == 1:
            self.failed.set()
            raise RuntimeError("temporary provider failure")
        self.recovered.set()
        return []


async def test_collector_loop_recovers_after_a_collection_error() -> None:
    collector = RecoveringCollector()
    shutdown_event = asyncio.Event()
    api_module._collector_status = {}
    task = asyncio.create_task(
        _run_collector_loop(
            collector=collector,
            scorer=RainbowScorer(),
            store=MagicMock(),
            interval_seconds=0.01,
            shutdown_event=shutdown_event,
        )
    )

    try:
        await asyncio.wait_for(collector.failed.wait(), timeout=1)
        await asyncio.sleep(0)
        assert api_module._collector_status[collector.name] == "error"

        await asyncio.wait_for(collector.recovered.wait(), timeout=1)
        assert collector.attempts >= 2
        assert api_module._collector_status[collector.name] == "running"
    finally:
        shutdown_event.set()
        await asyncio.wait_for(task, timeout=1)
