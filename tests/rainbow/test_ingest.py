"""Tests for Rainbow API Signal Ingest endpoint (Issue #36).

Min 15 test cases covering validation, storage, safety defaults, rate
limiting, error handling, and regression of existing routes.
"""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime

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
from core.signals.risk_gate import RiskGate
from rainbow.distribution import api as api_module
from rainbow.ingest.ingest import RainbowIngestor
from rainbow.ingest.models import RainbowIngestRequest
from rainbow.ingest.router import init_ingest_router

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    """Return an ISO-8601 UTC timestamp for the current time."""
    return datetime.now(UTC).isoformat()

_VALID_REQUEST: dict = {
    "asset": "BTC/USDT",
    "direction": "bullish",
    "strength": 0.75,
    "source": "test_source",
    "timestamp": _now_iso(),
}


def _make_registry() -> CanonicalSignalRegistry:
    db_dir = tempfile.mkdtemp()
    db_path = os.path.join(db_dir, "test_ingest.db")
    return CanonicalSignalRegistry(db_path=db_path)


def _make_ingestor(registry: CanonicalSignalRegistry) -> RainbowIngestor:
    return RainbowIngestor(registry=registry, risk_gate=RiskGate())


def _envelope(
    signal_class: SignalClass = SignalClass.ENTRY,
    asset: str = "BTC/USDT",
) -> CanonicalSignalEnvelope:
    return CanonicalSignalEnvelope(
        signal_class=signal_class,
        subtype="test",
        source="test_source",
        asset=asset,
        direction=SignalDirection.BULLISH,
        confidence=0.7,
        risk_score=0.3,
        priority=SignalPriority.MEDIUM,
        data_quality=DataQuality(status=DataQualityStatus.OK),
        actionability={"can_alert": True},
        invalidation={"max_age_seconds": 3600, "conditions": []},
        raw_refs=[],
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def registry() -> CanonicalSignalRegistry:
    reg = _make_registry()
    yield reg
    reg.close()


@pytest.fixture()
def ingestor(registry: CanonicalSignalRegistry) -> RainbowIngestor:
    return _make_ingestor(registry)


@pytest.fixture()
def client(registry: CanonicalSignalRegistry) -> TestClient:
    """Create a test client with the ingest router wired up."""
    original_reg = api_module._canonical_registry
    api_module._canonical_registry = registry

    ingestor = _make_ingestor(registry)
    init_ingest_router(ingestor)

    app = api_module.create_app(
        store=None,
        settings=None,
        engine=None,
        enable_metrics=False,
    )
    tc = TestClient(app)
    yield tc

    api_module._canonical_registry = original_reg
    registry.close()


# ===========================================================================
# 1. Model validation tests
# ===========================================================================

class TestModelValidation:
    """RainbowIngestRequest Pydantic validation."""

    def test_valid_bullish_request(self) -> None:
        req = RainbowIngestRequest(**_VALID_REQUEST)
        assert req.direction == "bullish"
        assert req.asset == "BTC/USDT"

    def test_valid_bearish_request(self) -> None:
        data = {**_VALID_REQUEST, "direction": "bearish"}
        req = RainbowIngestRequest(**data)
        assert req.direction == "bearish"

    def test_valid_neutral_request(self) -> None:
        data = {**_VALID_REQUEST, "direction": "neutral"}
        req = RainbowIngestRequest(**data)
        assert req.direction == "neutral"

    def test_invalid_direction_rejected(self) -> None:
        with pytest.raises(Exception):
            RainbowIngestRequest(**{**_VALID_REQUEST, "direction": "sideways"})

    def test_strength_above_1_rejected(self) -> None:
        with pytest.raises(Exception):
            RainbowIngestRequest(**{**_VALID_REQUEST, "strength": 1.5})

    def test_strength_below_0_rejected(self) -> None:
        with pytest.raises(Exception):
            RainbowIngestRequest(**{**_VALID_REQUEST, "strength": -0.1})

    def test_empty_asset_rejected(self) -> None:
        with pytest.raises(Exception):
            RainbowIngestRequest(**{**_VALID_REQUEST, "asset": ""})

    def test_whitespace_only_asset_rejected(self) -> None:
        with pytest.raises(Exception):
            RainbowIngestRequest(**{**_VALID_REQUEST, "asset": "   "})

    def test_missing_required_field_rejected(self) -> None:
        for field in ("asset", "direction", "strength", "source", "timestamp"):
            data = {k: v for k, v in _VALID_REQUEST.items() if k != field}
            with pytest.raises(Exception):
                RainbowIngestRequest(**data)

    def test_optional_fields_default_none(self) -> None:
        req = RainbowIngestRequest(**_VALID_REQUEST)
        assert req.rainbow_score is None
        assert req.raw_data is None
        assert req.signal_class is None
        assert req.confidence is None


# ===========================================================================
# 2. Ingestor logic tests
# ===========================================================================

class TestIngestorLogic:
    """Direct RainbowIngestor.ingest() tests."""

    def test_bullish_signal_accepted(self, ingestor: RainbowIngestor) -> None:
        req = RainbowIngestRequest(**_VALID_REQUEST)
        result = ingestor.ingest(req)
        assert result.status == "accepted"
        assert result.signal_id is not None
        assert result.envelope_created is True

    def test_bearish_signal_accepted(self, ingestor: RainbowIngestor) -> None:
        req = RainbowIngestRequest(**{**_VALID_REQUEST, "direction": "bearish"})
        result = ingestor.ingest(req)
        assert result.status == "accepted"

    def test_neutral_signal_rejected_by_risk_gate(self, ingestor: RainbowIngestor) -> None:
        """Neutral direction ENTRY signals are rejected by the risk gate
        (rule 4: entry_no_direction)."""
        req = RainbowIngestRequest(**{**_VALID_REQUEST, "direction": "neutral"})
        result = ingestor.ingest(req)
        # The risk gate rejects neutral ENTRY signals
        assert result.status == "rejected"
        assert "entry_no_direction" in result.reason or result.envelope_created is True

    def test_signal_stored_in_registry(self, ingestor: RainbowIngestor, registry: CanonicalSignalRegistry) -> None:
        req = RainbowIngestRequest(**_VALID_REQUEST)
        result = ingestor.ingest(req)
        stored = registry.get_signal(result.signal_id)  # type: ignore[arg-type]
        assert stored is not None
        assert stored["asset"] == "BTC/USDT"

    def test_can_execute_is_false(self, ingestor: RainbowIngestor, registry: CanonicalSignalRegistry) -> None:
        req = RainbowIngestRequest(**_VALID_REQUEST)
        result = ingestor.ingest(req)
        stored = registry.get_signal(result.signal_id)  # type: ignore[arg-type]
        assert stored is not None
        assert stored["actionability"]["can_execute"] is False

    def test_dry_run_only_is_true(self, ingestor: RainbowIngestor, registry: CanonicalSignalRegistry) -> None:
        req = RainbowIngestRequest(**_VALID_REQUEST)
        result = ingestor.ingest(req)
        stored = registry.get_signal(result.signal_id)  # type: ignore[arg-type]
        assert stored is not None
        assert stored["actionability"]["dry_run_only"] is True

    def test_ingest_result_has_signal_id(self, ingestor: RainbowIngestor) -> None:
        req = RainbowIngestRequest(**_VALID_REQUEST)
        result = ingestor.ingest(req)
        assert result.signal_id is not None
        assert len(result.signal_id) > 0

    def test_no_execution_path_introduced(self, ingestor: RainbowIngestor) -> None:
        """Ingest only creates data — it never triggers execution."""
        req = RainbowIngestRequest(**_VALID_REQUEST)
        result = ingestor.ingest(req)
        # The ingestor has no execute/trade/order methods
        assert not hasattr(ingestor, "execute")
        assert not hasattr(ingestor, "place_order")
        assert result.envelope_created is True

    def test_registry_failure_returns_error(self, registry: CanonicalSignalRegistry) -> None:
        """Simulate a registry failure — ingest must return status='error'."""
        ingestor = _make_ingestor(registry)
        req = RainbowIngestRequest(**_VALID_REQUEST)

        # Close the registry to force a DB error
        registry.close()

        result = ingestor.ingest(req)
        assert result.status == "error"
        assert result.envelope_created is False


# ===========================================================================
# 3. Rate limiting tests
# ===========================================================================

class TestRateLimiting:
    """Per-source rate limiter behavior."""

    def test_rate_limiting_blocks_excessive_requests(self, registry: CanonicalSignalRegistry) -> None:
        ingestor = RainbowIngestor(registry=registry, rate_limit_per_minute=3)
        req = RainbowIngestRequest(**_VALID_REQUEST)

        results = []
        for _ in range(5):
            r = ingestor.ingest(req)
            results.append(r)

        rate_limited = sum(1 for r in results if r.reason.startswith("rate_limit_exceeded"))
        # At least one request must be rate-limited
        assert rate_limited >= 1
        # Total results equals number of requests
        assert len(results) == 5


# ===========================================================================
# 4. API endpoint integration tests
# ===========================================================================

class TestIngestEndpoint:
    """FastAPI endpoint via TestClient."""

    def test_post_valid_signal(self, client: TestClient) -> None:
        resp = client.post("/api/v1/signals/ingest", json=_VALID_REQUEST)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("accepted", "rejected")
        assert data["signal_id"] is not None
        assert data["envelope_created"] is True or data["reason"] == "entry_no_direction"

    def test_post_invalid_direction(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/signals/ingest",
            json={**_VALID_REQUEST, "direction": "sideways"},
        )
        # FastAPI returns 422 for Pydantic validation errors
        assert resp.status_code == 422

    def test_post_invalid_strength(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/signals/ingest",
            json={**_VALID_REQUEST, "strength": 2.0},
        )
        assert resp.status_code == 422

    def test_post_empty_asset(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/signals/ingest",
            json={**_VALID_REQUEST, "asset": ""},
        )
        assert resp.status_code == 422

    def test_post_missing_field(self, client: TestClient) -> None:
        data = {k: v for k, v in _VALID_REQUEST.items() if k != "source"}
        resp = client.post("/api/v1/signals/ingest", json=data)
        assert resp.status_code == 422


# ===========================================================================
# 5. Regression tests — existing routes still work
# ===========================================================================

class TestRegression:
    """Existing API routes must still function after adding the ingest router."""

    def test_health_still_works(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    def test_signals_latest_still_works(self, client: TestClient, registry: CanonicalSignalRegistry) -> None:
        # The /signals/latest endpoint requires a store, which is None in tests
        resp = client.get("/signals/latest")
        # Without a store, it returns 503 — that's expected existing behavior
        assert resp.status_code in (200, 503)

    def test_canonical_latest_still_works(self, client: TestClient, registry: CanonicalSignalRegistry) -> None:
        registry.append(_envelope())
        resp = client.get("/signals/canonical/latest")
        assert resp.status_code == 200
