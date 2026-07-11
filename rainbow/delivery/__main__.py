"""Run the optional AI4Trade delivery worker once."""

from __future__ import annotations

import asyncio

from rainbow.delivery.client import AI4TradeClient, LocalRainbowProvider
from rainbow.delivery.heartbeat import AI4TradeHeartbeat, AI4TradeTaskHandler
from rainbow.delivery.models import AI4TradePayload, DeliveryConfig, DeliveryMode
from rainbow.delivery.worker import DeliveryWorker


class _ShadowSender:
    """A guard that makes external publication impossible in shadow mode."""

    async def publish(self, payload: AI4TradePayload) -> None:
        del payload
        raise RuntimeError("Shadow delivery must not publish externally")


def build_worker(config: DeliveryConfig) -> DeliveryWorker:
    """Build a worker without loading AI4Trade credentials outside live mode."""

    provider = LocalRainbowProvider(config.provider_base_url)
    heartbeat = None
    task_handler = None

    if config.mode is DeliveryMode.LIVE:
        sender = AI4TradeClient(config.token, config.ai4trade_base_url)
        if config.heartbeat_enabled:
            task_queue: asyncio.Queue[list[dict[str, object]]] = asyncio.Queue()
            heartbeat = AI4TradeHeartbeat(sender, task_queue)
            task_handler = AI4TradeTaskHandler(task_queue)
    else:
        sender = _ShadowSender()

    return DeliveryWorker(
        config,
        provider,
        sender,
        heartbeat=heartbeat,
        task_handler=task_handler,
    )


async def _main() -> None:
    config = DeliveryConfig.from_environment()
    if config.mode is DeliveryMode.OFF:
        return
    worker = build_worker(config)
    try:
        await worker.run_once()
    finally:
        await worker.close()


if __name__ == "__main__":
    asyncio.run(_main())
