from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

import httpx

from rainbow.models.signal import CryptoSignal

log = logging.getLogger(__name__)


class WebhookSubscription:
    def __init__(
        self,
        url: str,
        asset: str | None = None,
        source: str | None = None,
        signal_type: str | None = None,
        secret: str = "",
    ) -> None:
        self.url = url
        self.asset = asset
        self.source = source
        self.signal_type = signal_type
        self.secret = secret
        self.created_at = datetime.now(UTC)
        self.failures = 0
        self.last_success: datetime | None = None

    def matches(self, signal: CryptoSignal) -> bool:
        if self.asset and signal.asset != self.asset:
            return False
        if self.source and signal.source != self.source:
            return False
        if self.signal_type and signal.signal_type.value != self.signal_type:
            return False
        return True


class WebhookManager:
    MAX_FAILURES = 5

    def __init__(self) -> None:
        self._subscriptions: dict[str, WebhookSubscription] = {}
        self._client = httpx.AsyncClient(timeout=10.0)

    def subscribe(self, subscription: WebhookSubscription) -> str:
        sub_id = f"wh_{len(self._subscriptions)}_{int(subscription.created_at.timestamp())}"
        self._subscriptions[sub_id] = subscription
        log.info("Webhook registriert: %s -> %s", sub_id, subscription.url)
        return sub_id

    def unsubscribe(self, sub_id: str) -> bool:
        if sub_id in self._subscriptions:
            del self._subscriptions[sub_id]
            log.info("Webhook entfernt: %s", sub_id)
            return True
        return False

    def list_subscriptions(self) -> list[dict]:
        return [
            {
                "id": sid,
                "url": sub.url,
                "asset": sub.asset,
                "source": sub.source,
                "signal_type": sub.signal_type,
                "failures": sub.failures,
            }
            for sid, sub in self._subscriptions.items()
        ]

    async def dispatch(self, signal: CryptoSignal) -> None:
        payload = signal.model_dump_json()
        tasks = []

        for sub_id, sub in list(self._subscriptions.items()):
            if not sub.matches(signal):
                continue
            if sub.failures >= self.MAX_FAILURES:
                continue
            tasks.append(self._deliver(sub_id, sub, payload))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _deliver(
        self, sub_id: str, sub: WebhookSubscription, payload: str,
    ) -> None:
        headers = {"Content-Type": "application/json"}
        if sub.secret:
            headers["X-Webhook-Secret"] = sub.secret

        try:
            resp = await self._client.post(sub.url, content=payload, headers=headers)
            if resp.status_code < 400:
                sub.failures = 0
                sub.last_success = datetime.now(UTC)
            else:
                sub.failures += 1
                log.warning(
                    "Webhook %s: HTTP %d von %s", sub_id, resp.status_code, sub.url,
                )
        except httpx.HTTPError as exc:
            sub.failures += 1
            log.warning(
                "Webhook %s: Zustellung fehlgeschlagen an %s (%s)",
                sub_id, sub.url, type(exc).__name__,
            )

        if sub.failures >= self.MAX_FAILURES:
            log.error(
                "Webhook %s: Nach %d Fehlern deaktiviert", sub_id, sub.failures,
            )

    async def close(self) -> None:
        await self._client.aclose()
