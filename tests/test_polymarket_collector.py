"""Tests fuer PolymarketCollector (Issue #98)."""

import pytest

from rainbow.collectors.polymarket_collector import (
    CRYPTO_KEYWORDS,
    MIN_LIQUIDITY_USD,
    MIN_PROBABILITY,
    POLYMARKET_CLOB_URL,
    PROBABILITY_DEVIATION,
    PolymarketCollector,
)


class TestPolymarketCollectorDisabled:
    """Collector soll leer zurueckgeben wenn disabled."""

    @pytest.mark.asyncio
    async def test_collect_returns_empty_when_disabled(self):
        collector = PolymarketCollector(enabled=False)
        signals = await collector.collect()
        assert signals == []

    def test_name_is_polymarket(self):
        collector = PolymarketCollector()
        assert collector.name == "polymarket"

    def test_enabled_defaults_to_false(self):
        collector = PolymarketCollector()
        assert collector.enabled is False

    @pytest.mark.asyncio
    async def test_health_check_ok_when_disabled(self):
        collector = PolymarketCollector(enabled=False)
        assert await collector.health_check() is True


class TestPolymarketSignalFactories:
    """Signal-Factories sollen korrekte CryptoSignals erzeugen."""

    def test_prediction_bull_triggered(self):
        collector = PolymarketCollector()
        signal = collector._prediction_bull_signal("BTC", "Bitcoin above $100k by Dec?", 0.75)
        assert signal is not None
        assert signal.asset == "BTC"
        assert signal.signal_type.value == "prediction_market"
        assert signal.direction.value == "bullish"
        assert signal.raw_data["subtype"] == "PREDICTION_BULL_HIGH"

    def test_prediction_bull_below_threshold(self):
        collector = PolymarketCollector()
        signal = collector._prediction_bull_signal("BTC", "Bitcoin above $100k?", 0.60)
        assert signal is None

    def test_prediction_bear_triggered(self):
        collector = PolymarketCollector()
        signal = collector._prediction_bear_signal("ETH", "Ethereum below $1k?", 0.80)
        assert signal is not None
        assert signal.direction.value == "bearish"
        assert signal.raw_data["subtype"] == "PREDICTION_BEAR_HIGH"

    def test_macro_event_risk_triggered(self):
        collector = PolymarketCollector()
        signal = collector._macro_event_risk_signal("BTC", "SEC approves Bitcoin ETF?", 500_000)
        assert signal is not None
        assert signal.direction.value == "neutral"
        assert signal.raw_data["subtype"] == "MACRO_EVENT_RISK"

    def test_macro_event_risk_below_liquidity(self):
        collector = PolymarketCollector()
        signal = collector._macro_event_risk_signal("BTC", "Small market", 50_000)
        assert signal is None


class TestKeywordFilter:
    """Keyword-Filter soll nur crypto-relevante Maerkte erkennen."""

    def test_matches_bitcoin(self):
        assert PolymarketCollector._matches_crypto_keywords("Will Bitcoin hit $100k?") is True

    def test_matches_btc(self):
        assert PolymarketCollector._matches_crypto_keywords("BTC price prediction") is True

    def test_matches_ethereum(self):
        assert PolymarketCollector._matches_crypto_keywords("Ethereum merge outcome") is True

    def test_matches_sec(self):
        assert PolymarketCollector._matches_crypto_keywords("SEC crypto regulation 2026") is True

    def test_matches_fed(self):
        assert PolymarketCollector._matches_crypto_keywords("Fed interest rate decision") is True

    def test_no_match_irrelevant(self):
        assert PolymarketCollector._matches_crypto_keywords("Super Bowl winner 2027") is False

    def test_no_match_empty(self):
        assert PolymarketCollector._matches_crypto_keywords("") is False

    def test_case_insensitive(self):
        assert PolymarketCollector._matches_crypto_keywords("BITCOIN TO THE MOON") is True


class TestConstants:
    """Konstanten sollen den Issue-Spezifikationen entsprechen."""

    def test_min_liquidity(self):
        assert MIN_LIQUIDITY_USD == 100_000

    def test_min_probability(self):
        assert MIN_PROBABILITY == 0.65

    def test_probability_deviation(self):
        assert PROBABILITY_DEVIATION == 0.15

    def test_clob_url(self):
        assert POLYMARKET_CLOB_URL == "https://clob.polymarket.com"

    def test_keywords_contain_essentials(self):
        assert "bitcoin" in CRYPTO_KEYWORDS
        assert "btc" in CRYPTO_KEYWORDS
        assert "ethereum" in CRYPTO_KEYWORDS
        assert "eth" in CRYPTO_KEYWORDS
        assert "crypto" in CRYPTO_KEYWORDS
        assert "sec" in CRYPTO_KEYWORDS
        assert "fed" in CRYPTO_KEYWORDS
