"""Tests for the fail-closed /health contract with a startup grace period.

Rainbow must not report healthy=200 unless a fresh heartbeat exists, the
signal store is ready, and no collector is in an error state. During the
configurable startup grace period, a missing heartbeat is reported as
"starting" (still 503) rather than a hard "unhealthy" — otherwise Docker's
own healthcheck would flap the container before the first collector cycle
completes.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from core.heartbeat_writer import HeartbeatWriter
from rainbow.config.settings import RainbowSettings
from rainbow.distribution import api as api_module


def _make_client(tmp_path: Any, monkeypatch: Any, **settings_kwargs: Any) -> TestClient:
    heartbeat_path = tmp_path / "heartbeat_rainbow.json"
    monkeypatch.setattr(api_module, "HEARTBEAT_PATH", str(heartbeat_path))

    settings = RainbowSettings(**settings_kwargs)
    app = api_module.create_app(store=None, settings=settings, engine=None, enable_metrics=False)
    return TestClient(app)


def _write_heartbeat(tmp_path: Any, *, age_seconds: float = 0.0, status: str = "healthy") -> None:
    writer = HeartbeatWriter(tmp_path / "heartbeat_rainbow.json", component="rainbow")
    data = writer.write(status=status)
    if age_seconds:
        data["timestamp_unix"] -= age_seconds
        import json

        (tmp_path / "heartbeat_rainbow.json").write_text(json.dumps(data))


class TestStartupGracePeriod:
    def test_no_heartbeat_within_grace_returns_starting(self, tmp_path: Any, monkeypatch: Any) -> None:
        client = _make_client(tmp_path, monkeypatch, health_grace_period_seconds=60)
        resp = client.get("/health")
        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "starting"
        assert body["within_grace_period"] is True

    def test_no_heartbeat_past_grace_returns_unhealthy(self, tmp_path: Any, monkeypatch: Any) -> None:
        client = _make_client(tmp_path, monkeypatch, health_grace_period_seconds=0)
        resp = client.get("/health")
        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "unhealthy"
        assert body["within_grace_period"] is False


class TestFailClosedHealth:
    def test_fresh_heartbeat_store_ready_no_errors_is_healthy(self, tmp_path: Any, monkeypatch: Any) -> None:
        _write_heartbeat(tmp_path)
        client = _make_client(tmp_path, monkeypatch, health_grace_period_seconds=0)
        api_module._store = object()
        api_module._collector_status = {"ta": "running"}
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    def test_stale_heartbeat_is_unhealthy(self, tmp_path: Any, monkeypatch: Any) -> None:
        _write_heartbeat(tmp_path, age_seconds=999)
        client = _make_client(
            tmp_path, monkeypatch, health_grace_period_seconds=0, health_max_heartbeat_age_seconds=120,
        )
        api_module._store = object()
        resp = client.get("/health")
        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "unhealthy"
        assert body["heartbeat"]["fresh"] is False

    def test_store_not_ready_is_unhealthy(self, tmp_path: Any, monkeypatch: Any) -> None:
        _write_heartbeat(tmp_path)
        client = _make_client(tmp_path, monkeypatch, health_grace_period_seconds=0)
        api_module._store = None
        resp = client.get("/health")
        assert resp.status_code == 503
        assert resp.json()["store_ready"] is False

    def test_collector_error_is_unhealthy(self, tmp_path: Any, monkeypatch: Any) -> None:
        _write_heartbeat(tmp_path)
        client = _make_client(tmp_path, monkeypatch, health_grace_period_seconds=0)
        api_module._store = object()
        api_module._collector_status = {"ta": "running", "reddit": "error"}
        resp = client.get("/health")
        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "unhealthy"
        assert body["collectors_fresh"] is False

    def test_read_only_flag_reflected_in_body(self, tmp_path: Any, monkeypatch: Any) -> None:
        _write_heartbeat(tmp_path)
        client = _make_client(tmp_path, monkeypatch, health_grace_period_seconds=0, read_only=False)
        api_module._store = object()
        api_module._collector_status = {}
        resp = client.get("/health")
        assert resp.json()["read_only"] is False
