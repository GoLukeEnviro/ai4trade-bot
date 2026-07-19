"""Tests fuer OnChainCollector (Issue #95)."""

import pytest

from rainbow.collectors.onchain_collector import (
    COOLDOWN_SECONDS,
    INFLOW_SPIKE_MULTIPLIER,
    SOPR_CAPITULATION_THRESHOLD,
    WHALE_MIN_VALUE_USD,
    OnChainCollector,
)


class TestOnChainCollectorDisabled:
    """Collector soll leer zurueckgeben wenn disabled."""

    @pytest.mark.asyncio
    async def test_collect_returns_empty_when_disabled(self):
        collector = OnChainCollector(enabled=False)
        signals = await collector.collect()
        assert signals == []

    @pytest.mark.asyncio
    async def test_collect_returns_empty_without_api_keys(self):
        collector = OnChainCollector(enabled=True)  # keine API-Keys
        signals = await collector.collect()
        assert signals == []

    def test_name_is_onchain(self):
        collector = OnChainCollector()
        assert collector.name == "onchain"

    def test_enabled_defaults_to_false(self):
        collector = OnChainCollector()
        assert collector.enabled is False

    @pytest.mark.asyncio
    async def test_health_check_ok_when_disabled(self):
        collector = OnChainCollector(enabled=False)
        assert await collector.health_check() is True


class TestOnChainSignalFactories:
    """Signal-Factories sollen korrekte CryptoSignals erzeugen."""

    def test_exchange_inflow_spike_triggered(self):
        collector = OnChainCollector()
        signal = collector._exchange_inflow_signal("BTC", net_inflow=200_000, avg_30d=50_000)
        assert signal is not None
        assert signal.asset == "BTC"
        assert signal.signal_type.value == "onchain"
        assert signal.direction.value == "bearish"
        assert signal.raw_data["subtype"] == "EXCHANGE_INFLOW_SPIKE"

    def test_exchange_inflow_no_trigger_below_threshold(self):
        collector = OnChainCollector()
        signal = collector._exchange_inflow_signal("BTC", net_inflow=80_000, avg_30d=50_000)
        assert signal is None  # 80k < 2x 50k

    def test_exchange_outflow_spike_triggered(self):
        collector = OnChainCollector()
        signal = collector._exchange_outflow_signal("ETH", net_outflow=300_000, avg_30d=100_000)
        assert signal is not None
        assert signal.direction.value == "bullish"
        assert signal.raw_data["subtype"] == "EXCHANGE_OUTFLOW_SPIKE"

    def test_whale_transfer_triggered(self):
        collector = OnChainCollector()
        signal = collector._whale_transfer_signal("BTC", value_usd=10_000_000, from_exchange=True)
        assert signal is not None
        assert signal.direction.value == "neutral"
        assert signal.raw_data["subtype"] == "WHALE_TRANSFER_LARGE"

    def test_whale_transfer_below_minimum(self):
        collector = OnChainCollector()
        signal = collector._whale_transfer_signal("BTC", value_usd=1_000_000, from_exchange=False)
        assert signal is None

    def test_sopr_capitulation_triggered(self):
        collector = OnChainCollector()
        signal = collector._sopr_capitulation_signal("BTC", sopr=0.92)
        assert signal is not None
        assert signal.direction.value == "bullish"
        assert signal.raw_data["subtype"] == "SOPR_CAPITULATION"

    def test_sopr_no_trigger_above_threshold(self):
        collector = OnChainCollector()
        signal = collector._sopr_capitulation_signal("BTC", sopr=0.99)
        assert signal is None

    def test_stablecoin_inflow_triggered(self):
        collector = OnChainCollector()
        signal = collector._stablecoin_inflow_signal("ETH", inflow_usd=50_000_000)
        assert signal is not None
        assert signal.direction.value == "bullish"
        assert signal.raw_data["subtype"] == "STABLECOIN_INFLOW"

    def test_stablecoin_inflow_zero(self):
        collector = OnChainCollector()
        signal = collector._stablecoin_inflow_signal("ETH", inflow_usd=0)
        assert signal is None


class TestCooldown:
    """Cooldown soll max 1 Signal pro Asset pro Stunde erlauben."""

    def test_cooldown_not_active_initially(self):
        collector = OnChainCollector()
        assert collector._is_cooldown_active("BTC") is False

    def test_cooldown_active_after_signal(self):
        collector = OnChainCollector()
        collector._record_signal("BTC")
        assert collector._is_cooldown_active("BTC") is True

    def test_cooldown_per_asset_independent(self):
        collector = OnChainCollector()
        collector._record_signal("BTC")
        assert collector._is_cooldown_active("ETH") is False


class TestConstants:
    """Konstanten sollen den Issue-Spezifikationen entsprechen."""

    def test_whale_min_value(self):
        assert WHALE_MIN_VALUE_USD == 5_000_000

    def test_cooldown_seconds(self):
        assert COOLDOWN_SECONDS == 3600

    def test_inflow_spike_multiplier(self):
        assert INFLOW_SPIKE_MULTIPLIER == 2.0

    def test_sopr_threshold(self):
        assert SOPR_CAPITULATION_THRESHOLD == 0.97
