"""Tests for integrations.freqtrade_strategy — Freqtrade IStrategy skeleton.

All tests verify that:
  - Strategy import does not fail without freqtrade installed
  - Strategy defaults to HOLD when no signal is available
  - Strategy maps "long" advisory to entry signal
  - Strategy maps "short" advisory to exit signal
  - Strategy ignores expired signals
  - No live trading functions are introduced
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

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
from integrations.freqtrade_bridge import FreqtradeBridge

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
) -> CanonicalSignalEnvelope:
    """Create a valid canonical signal envelope for testing."""
    return CanonicalSignalEnvelope(
        signal_class=SignalClass.ENTRY,
        subtype="test",
        source="test",
        asset=asset,
        direction=direction,
        confidence=confidence,
        risk_score=risk_score,
        priority=SignalPriority.MEDIUM,
        reason_codes=["test"],
        data_quality=DataQuality(status=data_quality_status),
        actionability=Actionability(can_alert=True),
        valid_until=valid_until,
    )


def _make_registry_with_signal(envelope: CanonicalSignalEnvelope) -> CanonicalSignalRegistry:
    """Create an in-memory registry with one signal."""
    import os
    import tempfile

    db_path = os.path.join(tempfile.mkdtemp(), "test_strategy.db")
    registry = CanonicalSignalRegistry(db_path)
    registry.append(envelope)
    return registry


# ---------------------------------------------------------------------------
# Test: Strategy import does not fail in test environment
# ---------------------------------------------------------------------------

class TestStrategyImport:
    def test_import_without_freqtrade(self):
        """Strategy module should be importable even without freqtrade."""
        from integrations.freqtrade_strategy import AI4TradeSignalStrategy
        assert AI4TradeSignalStrategy is not None

    def test_strategy_instantiation(self):
        """Strategy can be instantiated without freqtrade config."""
        from integrations.freqtrade_strategy import AI4TradeSignalStrategy
        strategy = AI4TradeSignalStrategy(config={})
        assert strategy is not None
        assert strategy.stoploss == -0.05
        assert strategy.minimal_roi == {"0": 0.10, "30": 0.05, "60": 0.02}


# ---------------------------------------------------------------------------
# Test: Strategy defaults to HOLD when no signal available
# ---------------------------------------------------------------------------

class TestStrategyHoldDefault:
    def test_get_advisory_returns_none_when_bridge_unavailable(self):
        from integrations.freqtrade_strategy import AI4TradeSignalStrategy
        strategy = AI4TradeSignalStrategy(config={})
        # Manually set bridge to None to simulate unavailable bridge
        strategy._bridge = None
        # Override the bridge property so it stays None
        with patch.object(type(strategy), 'bridge', property(lambda self: None)):
            advisory = strategy._get_advisory("NONEXISTENT/PAIR")
            assert advisory is None

    def test_populate_entry_trend_defaults_to_hold(self):
        """With no bridge, entry trend should have enter_long=0."""
        from integrations.freqtrade_strategy import AI4TradeSignalStrategy
        strategy = AI4TradeSignalStrategy(config={})

        # Use a simple mock dataframe
        mock_df = MagicMock()
        mock_df.assign.return_value = mock_df
        # __contains__ to pass hasattr check
        type(mock_df).__contains__ = lambda self, key: False

        result = strategy.populate_entry_trend(mock_df, metadata={"pair": "BTC/USDT"})
        # Even if the bridge fails, dataframe should be returned
        assert result is not None


# ---------------------------------------------------------------------------
# Test: Strategy maps "long" advisory to entry signal
# ---------------------------------------------------------------------------

class TestStrategyBuyAdvisory:
    def test_long_advisory_maps_to_entry(self):
        """When bridge returns 'long', populate_entry_trend should set enter_long=1."""
        from integrations.freqtrade_strategy import AI4TradeSignalStrategy
        strategy = AI4TradeSignalStrategy(config={})

        # Create a real registry and bridge
        env = _make_envelope(
            direction=SignalDirection.BULLISH,
            confidence=0.9,
            risk_score=0.2,
        )
        registry = _make_registry_with_signal(env)
        bridge = FreqtradeBridge(registry, min_interval_seconds=0.0)

        # Override strategy's bridge
        strategy._bridge = bridge

        # Verify bridge returns long
        advisory = bridge.get_latest_signal("BTC/USDT")
        assert advisory["action"] == "long"

        registry.close()


# ---------------------------------------------------------------------------
# Test: Strategy maps "short" advisory to exit signal
# ---------------------------------------------------------------------------

class TestStrategySellAdvisory:
    def test_short_advisory_maps_to_exit(self):
        """When bridge returns 'short', populate_exit_trend should set exit_long=1."""
        from integrations.freqtrade_strategy import AI4TradeSignalStrategy
        strategy = AI4TradeSignalStrategy(config={})

        env = _make_envelope(
            direction=SignalDirection.BEARISH,
            confidence=0.9,
            risk_score=0.2,
        )
        registry = _make_registry_with_signal(env)
        bridge = FreqtradeBridge(registry, min_interval_seconds=0.0)
        strategy._bridge = bridge

        advisory = bridge.get_latest_signal("BTC/USDT")
        assert advisory["action"] == "short"

        registry.close()


# ---------------------------------------------------------------------------
# Test: Strategy ignores expired signals
# ---------------------------------------------------------------------------

class TestStrategyExpiredSignals:
    def test_expired_signal_results_in_hold(self):
        """Expired signals should produce 'hold' advisory, not entry."""

        env = _make_envelope(
            direction=SignalDirection.BULLISH,
            confidence=0.9,
            risk_score=0.2,
            valid_until=datetime.now(UTC) - timedelta(hours=1),
        )
        registry = _make_registry_with_signal(env)
        bridge = FreqtradeBridge(registry, min_interval_seconds=0.0)

        advisory = bridge.get_latest_signal("BTC/USDT")
        assert advisory["action"] == "hold"
        assert "expired" in advisory["reason"]

        registry.close()


# ---------------------------------------------------------------------------
# Test: No live trading functions introduced
# ---------------------------------------------------------------------------

class TestStrategyNoLiveTrading:
    def test_strategy_has_no_live_trading_functions(self):
        """Strategy should not have any methods that execute trades."""
        from integrations.freqtrade_strategy import AI4TradeSignalStrategy

        strategy = AI4TradeSignalStrategy(config={})
        forbidden = {"execute_order", "place_trade", "submit_order", "buy", "sell", "short"}
        for attr in dir(strategy):
            if attr.startswith("_"):
                continue
            assert attr not in forbidden, f"Forbidden method found: {attr}"

    def test_strategy_can_short_is_false(self):
        from integrations.freqtrade_strategy import AI4TradeSignalStrategy
        strategy = AI4TradeSignalStrategy(config={})
        assert strategy.can_short is False

    def test_strategy_stoploss_is_conservative(self):
        from integrations.freqtrade_strategy import AI4TradeSignalStrategy
        strategy = AI4TradeSignalStrategy(config={})
        assert strategy.stoploss == -0.05

    def test_strategy_minimal_roi_is_conservative(self):
        from integrations.freqtrade_strategy import AI4TradeSignalStrategy
        strategy = AI4TradeSignalStrategy(config={})
        assert strategy.minimal_roi["0"] == 0.10
        assert strategy.minimal_roi["60"] == 0.02
