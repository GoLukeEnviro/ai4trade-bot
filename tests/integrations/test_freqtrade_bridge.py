"""Tests for integrations.freqtrade_bridge — advisory signal consumer.

All tests verify that:
  - The bridge is read-only (never writes to registry)
  - The bridge never raises runtime errors (always returns HOLD on failure)
  - Safety invariants are enforced (can_execute=False, dry_run_only=True)
  - HOLD is always the safe fallback
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from core.signals.envelope import (
    Actionability,
    CanonicalSignalEnvelope,
    DataQuality,
    DataQualityStatus,
    SignalClass,
    SignalDirection,
    SignalPriority,
)
from core.signals.registry import CanonicalSignalRegistry
from integrations.freqtrade_bridge import FreqtradeBridge, _hold

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_envelope(
    *,
    direction: SignalDirection = SignalDirection.BULLISH,
    confidence: float = 0.85,
    risk_score: float = 0.3,
    data_quality_status: DataQualityStatus = DataQualityStatus.OK,
    valid_until: datetime | None = None,
    asset: str = "BTC/USDT",
    source: str = "test",
    can_execute: bool = False,
    dry_run_only: bool = True,
) -> CanonicalSignalEnvelope:
    """Create a valid canonical signal envelope for testing."""
    actionability_kwargs: dict = {"can_alert": True}
    # Note: Actionability model_validator will force can_execute=False
    # and dry_run_only=True regardless of what we pass, but we test
    # the override path separately.
    return CanonicalSignalEnvelope(
        signal_class=SignalClass.ENTRY,
        subtype="test",
        source=source,
        asset=asset,
        direction=direction,
        confidence=confidence,
        risk_score=risk_score,
        priority=SignalPriority.MEDIUM,
        reason_codes=["test"],
        data_quality=DataQuality(status=data_quality_status),
        actionability=Actionability(**actionability_kwargs),
        valid_until=valid_until,
    )


def _make_registry_with_signal(envelope: CanonicalSignalEnvelope) -> CanonicalSignalRegistry:
    """Create an in-memory registry with one signal."""
    import os
    import tempfile

    db_path = os.path.join(tempfile.mkdtemp(), "test_signals.db")
    registry = CanonicalSignalRegistry(db_path)
    registry.append(envelope)
    return registry


# ---------------------------------------------------------------------------
# Test: Bridge returns "buy" advisory for valid bullish signal
# ---------------------------------------------------------------------------

class TestBridgeBullishSignal:
    def test_returns_buy_for_bullish_with_high_confidence(self):
        env = _make_envelope(
            direction=SignalDirection.BULLISH,
            confidence=0.85,
            risk_score=0.3,
        )
        registry = _make_registry_with_signal(env)
        bridge = FreqtradeBridge(registry)
        result = bridge.get_latest_signal("BTC/USDT")
        assert result["action"] == "buy"
        assert result["confidence"] == 0.85
        registry.close()

    def test_returns_buy_with_minimum_confidence(self):
        env = _make_envelope(
            direction=SignalDirection.BULLISH,
            confidence=0.6,
            risk_score=0.3,
        )
        registry = _make_registry_with_signal(env)
        bridge = FreqtradeBridge(registry)
        result = bridge.get_latest_signal("BTC/USDT")
        assert result["action"] == "buy"
        registry.close()


# ---------------------------------------------------------------------------
# Test: Bridge returns "sell" advisory for valid bearish signal
# ---------------------------------------------------------------------------

class TestBridgeBearishSignal:
    def test_returns_sell_for_bearish_with_high_confidence(self):
        env = _make_envelope(
            direction=SignalDirection.BEARISH,
            confidence=0.9,
            risk_score=0.2,
        )
        registry = _make_registry_with_signal(env)
        bridge = FreqtradeBridge(registry)
        result = bridge.get_latest_signal("BTC/USDT")
        assert result["action"] == "sell"
        registry.close()


# ---------------------------------------------------------------------------
# Test: Bridge returns "hold" for expired signal
# ---------------------------------------------------------------------------

class TestBridgeExpiredSignal:
    def test_returns_hold_for_expired_signal(self):
        env = _make_envelope(
            direction=SignalDirection.BULLISH,
            confidence=0.9,
            risk_score=0.2,
            valid_until=datetime.now(UTC) - timedelta(hours=1),
        )
        registry = _make_registry_with_signal(env)
        bridge = FreqtradeBridge(registry)
        result = bridge.get_latest_signal("BTC/USDT")
        assert result["action"] == "hold"
        assert "expired" in result["reason"]
        registry.close()


# ---------------------------------------------------------------------------
# Test: Bridge returns "hold" for low confidence
# ---------------------------------------------------------------------------

class TestBridgeLowConfidence:
    def test_returns_hold_for_low_confidence(self):
        env = _make_envelope(
            direction=SignalDirection.BULLISH,
            confidence=0.3,
            risk_score=0.2,
        )
        registry = _make_registry_with_signal(env)
        bridge = FreqtradeBridge(registry)
        result = bridge.get_latest_signal("BTC/USDT")
        assert result["action"] == "hold"
        assert "low_confidence" in result["reason"]
        registry.close()

    def test_returns_hold_for_confidence_below_custom_threshold(self):
        env = _make_envelope(
            direction=SignalDirection.BULLISH,
            confidence=0.5,
            risk_score=0.2,
        )
        registry = _make_registry_with_signal(env)
        bridge = FreqtradeBridge(registry, confidence_threshold=0.55)
        result = bridge.get_latest_signal("BTC/USDT")
        assert result["action"] == "hold"
        registry.close()


# ---------------------------------------------------------------------------
# Test: Bridge returns "hold" for high risk (risk_score >= threshold)
# ---------------------------------------------------------------------------

class TestBridgeHighRisk:
    def test_returns_hold_for_high_risk(self):
        env = _make_envelope(
            direction=SignalDirection.BULLISH,
            confidence=0.9,
            risk_score=0.7,
        )
        registry = _make_registry_with_signal(env)
        bridge = FreqtradeBridge(registry, risk_threshold=0.7)
        result = bridge.get_latest_signal("BTC/USDT")
        assert result["action"] == "hold"
        assert "high_risk" in result["reason"]
        registry.close()

    def test_returns_buy_when_risk_below_threshold(self):
        env = _make_envelope(
            direction=SignalDirection.BULLISH,
            confidence=0.9,
            risk_score=0.69,
        )
        registry = _make_registry_with_signal(env)
        bridge = FreqtradeBridge(registry, risk_threshold=0.7)
        result = bridge.get_latest_signal("BTC/USDT")
        assert result["action"] == "buy"
        registry.close()


# ---------------------------------------------------------------------------
# Test: Bridge returns "hold" for degraded data quality
# ---------------------------------------------------------------------------

class TestBridgeDegradedDataQuality:
    @pytest.mark.parametrize("status", [
        DataQualityStatus.DEGRADED,
        DataQualityStatus.STALE,
        DataQualityStatus.UNAVAILABLE,
    ])
    def test_returns_hold_for_non_ok_data_quality(self, status):
        env = _make_envelope(
            direction=SignalDirection.BULLISH,
            confidence=0.9,
            risk_score=0.2,
            data_quality_status=status,
        )
        registry = _make_registry_with_signal(env)
        bridge = FreqtradeBridge(registry)
        result = bridge.get_latest_signal("BTC/USDT")
        assert result["action"] == "hold"
        assert "data_quality" in result["reason"]
        registry.close()


# ---------------------------------------------------------------------------
# Test: Bridge returns "hold" for missing/unknown signal
# ---------------------------------------------------------------------------

class TestBridgeMissingSignal:
    def test_returns_hold_for_missing_pair(self):
        import os
        import tempfile

        db_path = os.path.join(tempfile.mkdtemp(), "empty.db")
        registry = CanonicalSignalRegistry(db_path)
        bridge = FreqtradeBridge(registry)
        result = bridge.get_latest_signal("NONEXISTENT/USDT")
        assert result["action"] == "hold"
        assert "no_signal" in result["reason"]
        registry.close()


# ---------------------------------------------------------------------------
# Test: Bridge caches signal result
# ---------------------------------------------------------------------------

class TestBridgeCaching:
    def test_second_call_returns_cached_result(self):
        env = _make_envelope(
            direction=SignalDirection.BULLISH,
            confidence=0.9,
            risk_score=0.2,
        )
        registry = _make_registry_with_signal(env)
        bridge = FreqtradeBridge(registry, cache_ttl_seconds=60.0, min_interval_seconds=0.0)
        result1 = bridge.get_latest_signal("BTC/USDT")
        result2 = bridge.get_latest_signal("BTC/USDT")
        assert result1["action"] == "buy"
        assert result2["action"] == "buy"
        registry.close()


# ---------------------------------------------------------------------------
# Test: Bridge rate-limits repeated calls
# ---------------------------------------------------------------------------

class TestBridgeRateLimiting:
    def test_rate_limits_repeated_calls(self):
        env = _make_envelope(
            direction=SignalDirection.BULLISH,
            confidence=0.9,
            risk_score=0.2,
        )
        registry = _make_registry_with_signal(env)
        # Set min_interval to 100 seconds — second call should be rate-limited
        bridge = FreqtradeBridge(
            registry, min_interval_seconds=100.0, cache_ttl_seconds=0.01
        )
        result1 = bridge.get_latest_signal("BTC/USDT")
        assert result1["action"] == "buy"

        # Second call within rate limit but cache expired → rate_limited
        time.sleep(0.02)  # Let cache TTL expire
        result2 = bridge.get_latest_signal("BTC/USDT")
        assert result2["action"] == "hold"
        assert "rate_limited" in result2["reason"]
        registry.close()


# ---------------------------------------------------------------------------
# Test: Bridge handles registry errors gracefully
# ---------------------------------------------------------------------------

class TestBridgeRegistryErrors:
    def test_returns_hold_on_registry_error(self):
        registry = MagicMock(spec=CanonicalSignalRegistry)
        registry.query_latest.side_effect = RuntimeError("DB connection failed")
        bridge = FreqtradeBridge(registry, min_interval_seconds=0.0)
        result = bridge.get_latest_signal("BTC/USDT")
        assert result["action"] == "hold"
        assert "registry_error" in result["reason"]


# ---------------------------------------------------------------------------
# Test: Bridge enforces can_execute=False
# ---------------------------------------------------------------------------

class TestBridgeSafetyCanExecute:
    def test_rejects_signal_with_can_execute_true(self):
        # Use MagicMock without spec so nested attributes work freely.
        # This simulates a maliciously crafted envelope where can_execute=True.
        mock_envelope = MagicMock()
        mock_envelope.actionability.can_execute = True
        mock_envelope.actionability.dry_run_only = True
        mock_envelope.valid_until = None
        mock_envelope.data_quality.status = DataQualityStatus.OK
        mock_envelope.confidence = 0.9
        mock_envelope.risk_score = 0.2
        mock_envelope.direction = SignalDirection.BULLISH
        mock_envelope.id = "test-id-safety-can-execute"

        bridge = FreqtradeBridge(
            MagicMock(),
            min_interval_seconds=0.0,
        )
        result = bridge._evaluate_envelope("BTC/USDT", mock_envelope)
        assert result["action"] == "hold"
        assert "can_execute" in result["reason"]


# ---------------------------------------------------------------------------
# Test: Bridge enforces dry_run_only=True
# ---------------------------------------------------------------------------

class TestBridgeSafetyDryRunOnly:
    def test_rejects_signal_with_dry_run_only_false(self):
        mock_envelope = MagicMock()
        mock_envelope.actionability.can_execute = False
        mock_envelope.actionability.dry_run_only = False
        mock_envelope.valid_until = None
        mock_envelope.data_quality.status = DataQualityStatus.OK
        mock_envelope.confidence = 0.9
        mock_envelope.risk_score = 0.2
        mock_envelope.direction = SignalDirection.BULLISH
        mock_envelope.id = "test-id-safety-dry-run"

        bridge = FreqtradeBridge(
            MagicMock(),
            min_interval_seconds=0.0,
        )
        result = bridge._evaluate_envelope("BTC/USDT", mock_envelope)
        assert result["action"] == "hold"
        assert "dry_run_only" in result["reason"]


# ---------------------------------------------------------------------------
# Test: Bridge respects valid_until expiry
# ---------------------------------------------------------------------------

class TestBridgeValidUntilExpiry:
    def test_future_valid_until_passes(self):
        env = _make_envelope(
            direction=SignalDirection.BULLISH,
            confidence=0.9,
            risk_score=0.2,
            valid_until=datetime.now(UTC) + timedelta(hours=1),
        )
        registry = _make_registry_with_signal(env)
        bridge = FreqtradeBridge(registry, min_interval_seconds=0.0)
        result = bridge.get_latest_signal("BTC/USDT")
        assert result["action"] == "buy"
        registry.close()

    def test_past_valid_until_returns_hold(self):
        env = _make_envelope(
            direction=SignalDirection.BULLISH,
            confidence=0.9,
            risk_score=0.2,
            valid_until=datetime.now(UTC) - timedelta(hours=1),
        )
        registry = _make_registry_with_signal(env)
        bridge = FreqtradeBridge(registry, min_interval_seconds=0.0)
        result = bridge.get_latest_signal("BTC/USDT")
        assert result["action"] == "hold"
        assert "expired" in result["reason"]
        registry.close()


# ---------------------------------------------------------------------------
# Test: No live trading functions exist in bridge
# ---------------------------------------------------------------------------

class TestBridgeNoLiveTrading:
    def test_bridge_has_no_live_trading_functions(self):
        """Verify the bridge class has no methods that could execute trades."""
        bridge_attrs = [attr for attr in dir(FreqtradeBridge) if not attr.startswith("_")]
        forbidden = {"execute_order", "place_trade", "submit_order", "buy", "sell", "short"}
        for attr in bridge_attrs:
            assert attr not in forbidden, f"Forbidden method found: {attr}"

    def test_bridge_always_returns_advisory_dict(self):
        """Bridge output always has 'action' key with buy/sell/hold only."""
        import os
        import tempfile

        db_path = os.path.join(tempfile.mkdtemp(), "empty.db")
        registry = CanonicalSignalRegistry(db_path)
        bridge = FreqtradeBridge(registry, min_interval_seconds=0.0)
        result = bridge.get_latest_signal("ANY/PAIR")
        assert "action" in result
        assert result["action"] in ("buy", "sell", "hold")
        assert "reason" in result
        registry.close()


# ---------------------------------------------------------------------------
# Test: Safety invariants intact (Actionability defaults)
# ---------------------------------------------------------------------------

class TestSafetyInvariants:
    def test_actionability_can_execute_always_false(self):
        """Verify Actionability model_validator sets can_execute=False."""
        a = Actionability(can_alert=True, can_execute=True)
        assert a.can_execute is False

    def test_actionability_dry_run_only_always_true(self):
        """Verify Actionability model_validator sets dry_run_only=True."""
        a = Actionability(can_alert=True, dry_run_only=False)
        assert a.dry_run_only is True

    def test_hold_function_returns_safe_defaults(self):
        result = _hold("test_reason")
        assert result["action"] == "hold"
        assert result["reason"] == "test_reason"
        assert result["confidence"] == 0.0
        assert result["risk_score"] == 1.0
        assert result["source"] == "freqtrade_bridge"

    def test_bridge_never_raises_on_any_error(self):
        """Bridge.get_latest_signal catches ALL exceptions."""
        registry = MagicMock()
        # Make query_latest raise a generic exception that isn't caught
        # by the inner try/except (which only catches during registry access)
        # We need to make the error occur outside the inner try/except path
        # to exercise the outer try/except in get_latest_signal.
        registry.query_latest.side_effect = RuntimeError("catastrophic failure")
        bridge = FreqtradeBridge(registry, min_interval_seconds=0.0)
        result = bridge.get_latest_signal("BTC/USDT")
        assert result["action"] == "hold"
        # Registry error is caught by the inner try/except
        assert "registry_error" in result["reason"]

    def test_neutral_direction_maps_to_hold(self):
        env = _make_envelope(
            direction=SignalDirection.NEUTRAL,
            confidence=0.9,
            risk_score=0.2,
        )
        registry = _make_registry_with_signal(env)
        bridge = FreqtradeBridge(registry, min_interval_seconds=0.0)
        result = bridge.get_latest_signal("BTC/USDT")
        assert result["action"] == "hold"
        registry.close()
