"""HTTP clients owned exclusively by the optional delivery worker."""

from __future__ import annotations

from typing import Protocol

import httpx

from rainbow.delivery.models import AI4TradePayload


class RetryableDeliveryError(RuntimeError):
    pass


class AuthenticationDeliveryError(RuntimeError):
    pass


class PermanentDeliveryError(RuntimeError):
    pass


class SignalProvider(Protocol):
    async def fetch_latest(self) -> list[dict[str, object]]: ...


class SignalSender(Protocol):
    async def publish(self, payload: AI4TradePayload) -> None: ...


class LocalRainbowProvider:
    """Read signals through the local, GET-only Rainbow API boundary."""

    def __init__(self, base_url: str) -> None:
        self._client = httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=10.0)

    async def fetch_latest(self) -> list[dict[str, object]]:
        response = await self._client.get("/signals/latest")
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            raise PermanentDeliveryError("Rainbow /signals/latest response must be a list")
        return [item for item in data if isinstance(item, dict)]

    async def close(self) -> None:
        await self._client.aclose()


class AI4TradeClient:
    def __init__(self, token: str, base_url: str) -> None:
        if not token:
            raise ValueError("AI4TRADE_TOKEN is required for live delivery")
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=15.0,
        )

    async def publish(self, payload: AI4TradePayload) -> None:
        try:
            response = await self._client.post("/signals/realtime", json=payload.as_request_json())
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise RetryableDeliveryError(type(exc).__name__) from exc

        if response.status_code == 401:
            raise AuthenticationDeliveryError("AI4Trade authentication rejected")
        if response.status_code == 429 or response.status_code >= 500:
            raise RetryableDeliveryError(f"AI4Trade HTTP {response.status_code}")
        if response.status_code >= 400:
            raise PermanentDeliveryError(f"AI4Trade HTTP {response.status_code}")

        body = response.json()
        if not isinstance(body, dict) or not body.get("success"):
            raise RetryableDeliveryError("AI4Trade response did not confirm success")

    async def heartbeat(self) -> dict[str, object]:
        response = await self._client.post("/claw/agents/heartbeat")
        response.raise_for_status()
        body = response.json()
        return body if isinstance(body, dict) else {}

    async def close(self) -> None:
        await self._client.aclose()
