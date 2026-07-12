"""Tests for the read-only runtime guard on Rainbow's mutating routes.

Rainbow must never accept writes (webhook subscribe/unsubscribe, signal
ingest) while ``RainbowSettings.read_only`` is true. GET routes must keep
working regardless of the flag.
"""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from core.signals.registry import CanonicalSignalRegistry
from core.signals.risk_gate import RiskGate
from rainbow.config.settings import RainbowSettings
from rainbow.distribution import api as api_module
from rainbow.distribution.webhooks import WebhookManager
from rainbow.ingest.ingest import RainbowIngestor
from rainbow.ingest.router import init_ingest_router


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


_VALID_INGEST_BODY: dict = {
    "asset": "BTC/USDT",
    "direction": "bullish",
    "strength": 0.75,
    "source": "test_source",
    "timestamp": _now_iso(),
}


@pytest.fixture()
def registry() -> Any:
    db_dir = tempfile.mkdtemp()
    reg = CanonicalSignalRegistry(db_path=os.path.join(db_dir, "test.db"))
    yield reg
    reg.close()


def _make_client(registry: Any, *, read_only: bool) -> TestClient:
    original_reg = api_module._canonical_registry
    api_module._canonical_registry = registry

    init_ingest_router(RainbowIngestor(registry=registry, risk_gate=RiskGate()))

    settings = RainbowSettings(read_only=read_only)
    app = api_module.create_app(store=None, settings=settings, engine=None, enable_metrics=False)
    # Mirrors the module-global wiring RainbowEngine.initialize() normally
    # does at lifespan startup (not exercised here since engine=None).
    api_module._webhook_manager = WebhookManager()
    api_module._canonical_registry = original_reg
    return TestClient(app)


class TestWebhooksBlockedWhenReadOnly:
    def test_subscribe_returns_405(self, registry: Any) -> None:
        client = _make_client(registry, read_only=True)
        resp = client.post("/webhooks/subscribe", json={"url": "https://example.com/hook"})
        assert resp.status_code == 405

    def test_unsubscribe_returns_405(self, registry: Any) -> None:
        client = _make_client(registry, read_only=True)
        resp = client.delete("/webhooks/some-id")
        assert resp.status_code == 405

    def test_webhook_list_get_still_works(self, registry: Any) -> None:
        client = _make_client(registry, read_only=True)
        resp = client.get("/webhooks")
        assert resp.status_code == 200


class TestIngestBlockedWhenReadOnly:
    def test_ingest_returns_405(self, registry: Any) -> None:
        client = _make_client(registry, read_only=True)
        resp = client.post("/api/v1/signals/ingest", json=_VALID_INGEST_BODY)
        assert resp.status_code == 405


class TestMutationsAllowedWhenNotReadOnly:
    def test_subscribe_succeeds(self, registry: Any) -> None:
        client = _make_client(registry, read_only=False)
        resp = client.post("/webhooks/subscribe", json={"url": "https://example.com/hook"})
        assert resp.status_code == 200

    def test_ingest_succeeds(self, registry: Any) -> None:
        client = _make_client(registry, read_only=False)
        resp = client.post("/api/v1/signals/ingest", json=_VALID_INGEST_BODY)
        assert resp.status_code == 200
