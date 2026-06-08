from __future__ import annotations

import time
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from rainbow.distribution.webhooks import WebhookManager, WebhookSubscription

_start_time: float = 0.0
_store: Any = None
_settings: Any = None
_engine: Any = None
_collector_status: dict[str, str] = {}
_webhook_manager: WebhookManager | None = None


class WebhookSubscribeRequest(BaseModel):
    url: str
    asset: str | None = None
    source: str | None = None
    signal_type: str | None = None
    secret: str = ""


def create_app(store: Any, settings: Any, engine: Any = None, enable_metrics: bool = True) -> FastAPI:
    """FastAPI-App mit injizierten Abhaengigkeiten erstellen."""
    global _store, _settings, _engine, _start_time, _collector_status

    _store = store
    _settings = settings
    _engine = engine
    _start_time = time.monotonic()
    _collector_status = {}

    app = FastAPI(title="Rainbow Intelligence Engine", version="0.1.0")
    _register_routes(app)

    if enable_metrics:
        from prometheus_fastapi_instrumentator import Instrumentator
        from prometheus_fastapi_instrumentator import metrics as instr_metrics

        Instrumentator().add(
            instr_metrics.default(metric_namespace="rainbow"),
        ).instrument(app).expose(app, endpoint="/metrics/prometheus", include_in_schema=False)

    return app


def _register_routes(app: FastAPI) -> None:
    @app.get("/health")
    async def health() -> dict[str, Any]:
        uptime = time.monotonic() - _start_time
        return {
            "status": "healthy",
            "collectors": _collector_status,
            "uptime_seconds": round(uptime, 1),
        }

    @app.get("/signals/latest")
    async def signals_latest(
        asset: str | None = Query(default=None),
        source: str | None = Query(default=None),
        signal_type: str | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=500),
    ) -> list[dict[str, Any]]:
        if _store is None:
            raise HTTPException(status_code=503, detail="Signal store not ready")

        return await _store.get_latest(
            asset=asset,
            source=source,
            signal_type=signal_type,
            limit=limit,
        )

    @app.get("/signals/{signal_id}")
    async def signal_by_id(signal_id: str) -> dict[str, Any]:
        if _store is None:
            raise HTTPException(status_code=503, detail="Signal store not ready")

        signal = await _store.get_by_id(signal_id)
        if signal is None:
            raise HTTPException(status_code=404, detail=f"Signal '{signal_id}' not found")
        return signal

    @app.post("/signals/ingest")
    async def signals_ingest(body: dict[str, Any]) -> dict[str, Any]:
        """Internal endpoint: accept external signals (e.g. from legacy strategy).

        Accepts a JSON body matching legacy Signal fields and converts via
        SignalAdapter to CryptoSignal-compatible format before storing.
        Returns 202 Accepted with signal_id.
        """
        if _store is None:
            raise HTTPException(status_code=503, detail="Signal store not ready")

        from core.signal_adapter import SignalAdapter
        from rainbow.models.signal import CryptoSignal, Direction, SignalType

        # Detect legacy format (has 'pair' or 'action' keys) vs native Rainbow
        is_legacy = "pair" in body or "action" in body

        if is_legacy:
            # Legacy Signal -> Rainbow via SignalAdapter
            adapter = SignalAdapter()
            legacy_signal = adapter.rainbow_dict_to_signal(body)
            rainbow_dict = adapter.legacy_signal_to_rainbow(legacy_signal)
        else:
            rainbow_dict = body

        try:
            signal_type_raw = rainbow_dict.get("signal_type", "technical")
            signal_type = SignalType(signal_type_raw)
        except ValueError:
            signal_type = SignalType.TECHNICAL

        try:
            direction_raw = rainbow_dict.get("direction", "neutral")
            direction = Direction(direction_raw)
        except ValueError:
            direction = Direction.NEUTRAL

        sig = CryptoSignal(
            source=rainbow_dict.get("source", "external"),
            asset=rainbow_dict.get("asset", "UNKNOWN"),
            signal_type=signal_type,
            direction=direction,
            strength=float(rainbow_dict.get("strength", 0.0)),
            confidence=float(rainbow_dict.get("confidence", 0.0)),
            value=rainbow_dict.get("value"),
            raw_data=rainbow_dict.get("raw_data"),
            metadata=rainbow_dict.get("metadata", {}),
        )

        await _store.save(sig)
        return {"status": "accepted", "signal_id": sig.signal_id}

    @app.get("/metrics")
    async def metrics() -> dict[str, Any]:
        if _store is None:
            raise HTTPException(status_code=503, detail="Signal store not ready")

        latest = await _store.get_latest(limit=1)
        stored_count = len(latest)

        active_collectors = sum(1 for v in _collector_status.values() if v == "running")

        return {
            "signals_stored_count": stored_count,
            "collectors_active": active_collectors,
            "collectors_total": len(_collector_status),
        }

    # --- Webhook-Endpoints ---

    @app.post("/webhooks/subscribe")
    async def webhook_subscribe(body: WebhookSubscribeRequest) -> dict[str, str]:
        if _webhook_manager is None:
            raise HTTPException(status_code=503, detail="Webhook manager not ready")

        subscription = WebhookSubscription(
            url=body.url,
            asset=body.asset,
            source=body.source,
            signal_type=body.signal_type,
            secret=body.secret,
        )
        sub_id = _webhook_manager.subscribe(subscription)
        return {"subscription_id": sub_id}

    @app.delete("/webhooks/{sub_id}")
    async def webhook_unsubscribe(sub_id: str) -> dict[str, bool]:
        if _webhook_manager is None:
            raise HTTPException(status_code=503, detail="Webhook manager not ready")

        removed = _webhook_manager.unsubscribe(sub_id)
        if not removed:
            raise HTTPException(status_code=404, detail=f"Subscription '{sub_id}' not found")
        return {"removed": True}

    @app.get("/webhooks")
    async def webhook_list() -> list[dict]:
        if _webhook_manager is None:
            raise HTTPException(status_code=503, detail="Webhook manager not ready")

        return _webhook_manager.list_subscriptions()
