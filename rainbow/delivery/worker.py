"""Isolated, opt-in worker for external AI4Trade signal transport."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Protocol

from rainbow.delivery.client import (
    AuthenticationDeliveryError,
    PermanentDeliveryError,
    RetryableDeliveryError,
    SignalProvider,
    SignalSender,
)
from rainbow.delivery.models import DeliveryConfig, DeliveryMode, DeliveryRunResult
from rainbow.delivery.outbox import DeliveryOutbox
from rainbow.delivery.policy import DeliveryPolicy


class Heartbeat(Protocol):
    poll_once: Callable[[], Awaitable[None]]


class TaskHandler(Protocol):
    process_pending: Callable[[], Awaitable[int]]


class DeliveryWorker:
    def __init__(
        self,
        config: DeliveryConfig,
        provider: SignalProvider,
        sender: SignalSender,
        *,
        heartbeat: Heartbeat | None = None,
        task_handler: TaskHandler | None = None,
    ) -> None:
        self.config = config
        self._provider = provider
        self._sender = sender
        self.outbox = DeliveryOutbox(config.outbox_path)
        self._policy = DeliveryPolicy(config)
        self._heartbeat = heartbeat
        self._task_handler = task_handler

    async def run_once(self) -> DeliveryRunResult:
        if self.config.mode is DeliveryMode.OFF:
            return DeliveryRunResult(mode=DeliveryMode.OFF)

        await self.outbox.start()
        signals = await self._provider.fetch_latest()
        skipped = 0
        shadowed = 0
        for signal in signals:
            result = self._policy.evaluate(signal, now=datetime.now(UTC))
            if result.payload is None:
                skipped += 1
                continue
            status = "shadow" if self.config.mode is DeliveryMode.SHADOW else "pending"
            created = await self.outbox.enqueue(result.payload, status=status)
            if created and self.config.mode is DeliveryMode.SHADOW:
                shadowed += 1

        if self.config.heartbeat_enabled and self._heartbeat is not None:
            await self._heartbeat.poll_once()
            if self._task_handler is not None:
                await self._task_handler.process_pending()

        if self.config.mode is DeliveryMode.SHADOW:
            return DeliveryRunResult(mode=self.config.mode, skipped=skipped, shadowed=shadowed)

        sent = retried = dead_lettered = 0
        auth_failed = False
        for entry in await self.outbox.pending():
            try:
                await self._sender.publish(entry.payload)
            except AuthenticationDeliveryError:
                await self.outbox.mark_dead_letter(entry.payload.fingerprint, "authentication_failed")
                auth_failed = True
                dead_lettered += 1
                break
            except RetryableDeliveryError as exc:
                attempts = await self.outbox.mark_retrying(entry.payload.fingerprint, str(exc))
                if attempts >= self.config.max_attempts:
                    await self.outbox.mark_dead_letter(entry.payload.fingerprint, str(exc))
                    dead_lettered += 1
                else:
                    retried += 1
            except PermanentDeliveryError as exc:
                await self.outbox.mark_dead_letter(entry.payload.fingerprint, str(exc))
                dead_lettered += 1
            else:
                await self.outbox.mark_sent(entry.payload.fingerprint)
                sent += 1

        return DeliveryRunResult(
            mode=self.config.mode,
            skipped=skipped,
            sent=sent,
            retried=retried,
            dead_lettered=dead_lettered,
            auth_failed=auth_failed,
        )

    async def close(self) -> None:
        await self.outbox.close()
        for dependency in (self._provider, self._sender):
            close = getattr(dependency, "close", None)
            if close is not None:
                await close()
