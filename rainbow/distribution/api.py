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
_canonical_registry: Any = None


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
    # --- Ingest router (Issue #36) ---
    from rainbow.ingest.router import init_ingest_router
    from rainbow.ingest.router import router as ingest_router

    app.include_router(ingest_router)
    if _canonical_registry is not None:
        from core.signals.risk_gate import RiskGate
        from rainbow.ingest.ingest import RainbowIngestor

        _ingestor = RainbowIngestor(
            registry=_canonical_registry,
            risk_gate=RiskGate(),
        )
        init_ingest_router(_ingestor)

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
            asset=asset, source=source, signal_type=signal_type, limit=limit,
        )

    @app.get("/signals/{signal_id}")
    async def signal_by_id(signal_id: str) -> dict[str, Any]:
        if _store is None:
            raise HTTPException(status_code=503, detail="Signal store not ready")

        signal = await _store.get_by_id(signal_id)
        if signal is None:
            raise HTTPException(status_code=404, detail=f"Signal '{signal_id}' not found")
        return signal

    @app.get("/metrics")
    async def metrics() -> dict[str, Any]:
        if _store is None:
            raise HTTPException(status_code=503, detail="Signal store not ready")

        stored_count = await _store.count()

        active_collectors = sum(
            1 for v in _collector_status.values() if v == "running"
        )

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

    # --- Canonical Signal Endpoints (Issue #18) ---

    @app.get("/signals/canonical/latest")
    async def canonical_signals_latest(
        asset: str | None = Query(default=None),
        signal_class: str | None = Query(default=None, alias="class"),
        limit: int = Query(default=50, ge=1, le=500),
    ) -> list[dict[str, Any]]:
        if _canonical_registry is None:
            raise HTTPException(status_code=503, detail="Canonical registry not ready")

        from core.signals.envelope import SignalClass as SC

        sc = None
        if signal_class is not None:
            try:
                sc = SC(signal_class)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid signal class: {signal_class}",
                )
        return _canonical_registry.query_latest(asset=asset, signal_class=sc, limit=limit)

    @app.get("/risk/latest")
    async def risk_latest(
        limit: int = Query(default=50, ge=1, le=500),
    ) -> list[dict[str, Any]]:
        if _canonical_registry is None:
            raise HTTPException(status_code=503, detail="Canonical registry not ready")

        from core.signals.envelope import SignalClass as SC

        risk_signals = _canonical_registry.query_latest(
            signal_class=SC.RISK, limit=limit,
        )
        dq_signals = _canonical_registry.query_latest(
            signal_class=SC.DATA_QUALITY, limit=limit,
        )
        combined = risk_signals + dq_signals
        combined.sort(key=lambda s: s.get("created_at", ""), reverse=True)
        return combined[:limit]

    @app.get("/context/agent-summary")
    async def agent_summary() -> dict[str, str]:
        from core.signals.summarizer import format_signal_summary

        if _canonical_registry is None:
            raise HTTPException(status_code=503, detail="Canonical registry not ready")

        latest = _canonical_registry.query_latest(limit=5)
        lines: list[str] = []
        for entry in latest:
            from core.signals.envelope import CanonicalSignalEnvelope

            env = CanonicalSignalEnvelope(**entry)
            lines.append(format_signal_summary(env))

        summary_text = "\n".join(lines) if lines else "No signals available."
        return {"summary": summary_text}
