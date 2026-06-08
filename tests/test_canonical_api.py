"""Tests for canonical API endpoints (Issue #18)."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from core.signals.envelope import (
    CanonicalSignalEnvelope,
    DataQuality,
    DataQualityStatus,
    SignalClass,
    SignalDirection,
    SignalPriority,
)
from core.signals.registry import CanonicalSignalRegistry
from rainbow.distribution import api as api_module


def _envelope(
    signal_class: SignalClass = SignalClass.ENTRY,
    asset: str = "BTC/USDT",
    priority: SignalPriority = SignalPriority.MEDIUM,
) -> CanonicalSignalEnvelope:
    return CanonicalSignalEnvelope(
        signal_class=signal_class,
        subtype="test",
        source="test_source",
        asset=asset,
        direction=SignalDirection.BULLISH,
        confidence=0.7,
        risk_score=0.3,
        priority=priority,
        data_quality=DataQuality(status=DataQualityStatus.OK),
        actionability={"can_alert": True},
        invalidation={"max_age_seconds": 3600, "conditions": []},
        raw_refs=[],
    )


@pytest.fixture()
def _setup_registry(tmp_path: Any) -> Any:
    """Set up a temporary canonical registry on the api module."""
    db_path = str(tmp_path / "test_canonical.db")
    registry = CanonicalSignalRegistry(db_path=db_path)
    original = api_module._canonical_registry
    api_module._canonical_registry = registry
    yield registry
    api_module._canonical_registry = original
    registry.close()


@pytest.fixture()
def client(_setup_registry: Any) -> TestClient:
    """Create a test client with canonical registry wired up."""
    app = api_module.create_app(
        store=None,
        settings=None,
        engine=None,
        enable_metrics=False,
    )
    return TestClient(app)


class TestCanonicalLatest:
    def test_returns_signals(self, client: TestClient, _setup_registry: CanonicalSignalRegistry) -> None:
        env = _envelope()
        _setup_registry.append(env)

        resp = client.get("/signals/canonical/latest")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["asset"] == "BTC/USDT"

    def test_filter_by_asset(self, client: TestClient, _setup_registry: CanonicalSignalRegistry) -> None:
        _setup_registry.append(_envelope(asset="BTC/USDT"))
        _setup_registry.append(_envelope(asset="ETH/USDT"))

        resp = client.get("/signals/canonical/latest", params={"asset": "BTC/USDT"})
        assert resp.status_code == 200
        data = resp.json()
        assert all(s["asset"] == "BTC/USDT" for s in data)

    def test_filter_by_class(self, client: TestClient, _setup_registry: CanonicalSignalRegistry) -> None:
        _setup_registry.append(_envelope(signal_class=SignalClass.ENTRY))
        _setup_registry.append(_envelope(signal_class=SignalClass.RISK))

        resp = client.get("/signals/canonical/latest", params={"class": "entry"})
        assert resp.status_code == 200
        data = resp.json()
        assert all(s.get("signal_class") == "entry" for s in data)

    def test_limit_param(self, client: TestClient, _setup_registry: CanonicalSignalRegistry) -> None:
        for i in range(5):
            _setup_registry.append(_envelope(asset=f"ASSET{i}/USDT"))

        resp = client.get("/signals/canonical/latest", params={"limit": 2})
        assert resp.status_code == 200
        assert len(resp.json()) <= 2


class TestRiskLatest:
    def test_returns_risk_and_dq_signals(
        self,
        client: TestClient,
        _setup_registry: CanonicalSignalRegistry,
    ) -> None:
        _setup_registry.append(_envelope(signal_class=SignalClass.RISK))
        _setup_registry.append(_envelope(signal_class=SignalClass.DATA_QUALITY))
        _setup_registry.append(_envelope(signal_class=SignalClass.ENTRY))

        resp = client.get("/risk/latest")
        assert resp.status_code == 200
        data = resp.json()
        classes = {s.get("signal_class") for s in data}
        assert "risk" in classes or "data_quality" in classes
        assert "entry" not in classes

    def test_503_when_no_registry(self) -> None:
        original = api_module._canonical_registry
        api_module._canonical_registry = None
        try:
            app = api_module.create_app(store=None, settings=None, enable_metrics=False)
            tc = TestClient(app)
            resp = tc.get("/risk/latest")
            assert resp.status_code == 503
        finally:
            api_module._canonical_registry = original


class TestAgentSummary:
    def test_returns_summary(
        self,
        client: TestClient,
        _setup_registry: CanonicalSignalRegistry,
    ) -> None:
        _setup_registry.append(_envelope())

        resp = client.get("/context/agent-summary")
        assert resp.status_code == 200
        data = resp.json()
        assert "summary" in data
        assert "BTC/USDT" in data["summary"]

    def test_no_signals_available(self, client: TestClient) -> None:
        resp = client.get("/context/agent-summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"] == "No signals available."
