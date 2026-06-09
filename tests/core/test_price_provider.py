"""Tests for StaticPriceProvider stub improvements.

Verifies:
  - get_price returns 0.0 by default
  - is_stub() returns True
  - Warning is logged on first call to get_price
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from core.outcomes.price_provider import StaticPriceProvider


class TestStaticPriceProviderStub:
    """StaticPriceProvider is a documented stub."""

    def test_get_price_returns_default_zero(self):
        provider = StaticPriceProvider()
        result = provider.get_price("BTC/USDT", datetime.now(timezone.utc))
        assert result == 0.0

    def test_is_stub_returns_true(self):
        assert StaticPriceProvider.is_stub() is True

    def test_instance_is_stub(self):
        provider = StaticPriceProvider()
        assert provider.is_stub() is True

    def test_warning_logged_on_first_call(self, caplog):
        # Reset the class-level flag so we see the warning
        StaticPriceProvider._warned = False
        provider = StaticPriceProvider()
        with caplog.at_level(logging.WARNING, logger="core.outcomes.price_provider"):
            provider.get_price("ETH/USDT", datetime.now(timezone.utc))
        assert "StaticPriceProvider is a stub" in caplog.text
        # Reset for other tests
        StaticPriceProvider._warned = False

    def test_warning_only_once(self, caplog):
        StaticPriceProvider._warned = False
        provider = StaticPriceProvider()
        with caplog.at_level(logging.WARNING, logger="core.outcomes.price_provider"):
            provider.get_price("ETH/USDT", datetime.now(timezone.utc))
            provider.get_price("BTC/USDT", datetime.now(timezone.utc))
        # Only one warning across two calls
        warning_count = sum(
            1 for r in caplog.records if "StaticPriceProvider is a stub" in r.message
        )
        assert warning_count == 1
        StaticPriceProvider._warned = False
