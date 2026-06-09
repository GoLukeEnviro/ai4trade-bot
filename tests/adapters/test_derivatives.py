"""Tests for adapters.derivatives — dry-run-only scaffold.

All tests verify:
  - DryRunFetcher returns stub data when ENABLED
  - DryRunFetcher returns None when DISABLED (default)
  - Feature flag defaults to False
  - get_funding_rate never raises
  - get_open_interest never raises
  - Models validate correctly
  - DerivativesSignal combines data correctly
  - Adapter returns None when fetcher disabled
  - Adapter logs stub usage
  - No network calls are made
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from adapters.derivatives.adapter import DerivativesAdapter
from adapters.derivatives.client import DryRunDerivativesFetcher
from adapters.derivatives.models import DerivativesSignal, FundingRate, OpenInterest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    """Run an async coroutine synchronously in tests."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Model validation
# ---------------------------------------------------------------------------

class TestFundingRateModel:
    def test_valid_funding_rate(self):
        fr = FundingRate(
            symbol="BTC/USDT",
            rate=0.01,
            timestamp=datetime.now(UTC),
            next_funding_time=None,
            exchange="dry_run_stub",
        )
        assert fr.symbol == "BTC/USDT"
        assert fr.rate == 0.01
        assert fr.exchange == "dry_run_stub"

    def test_funding_rate_defaults(self):
        fr = FundingRate(
            symbol="ETH/USDT",
            rate=0.0001,
            timestamp=datetime.now(UTC),
        )
        assert fr.next_funding_time is None
        assert fr.exchange == "dry_run_stub"

    def test_funding_rate_with_next_funding_time(self):
        nf = datetime.now(UTC)
        fr = FundingRate(
            symbol="SOL/USDT",
            rate=0.02,
            timestamp=datetime.now(UTC),
            next_funding_time=nf,
        )
        assert fr.next_funding_time == nf

    def test_funding_rate_requires_symbol(self):
        with pytest.raises(Exception):
            FundingRate(rate=0.01, timestamp=datetime.now(UTC))

    def test_funding_rate_requires_rate(self):
        with pytest.raises(Exception):
            FundingRate(symbol="BTC/USDT", timestamp=datetime.now(UTC))

    def test_funding_rate_requires_timestamp(self):
        with pytest.raises(Exception):
            FundingRate(symbol="BTC/USDT", rate=0.01)

    def test_funding_rate_negative_rate_is_allowed(self):
        """Negative funding rates are legitimate (shorts pay longs)."""
        fr = FundingRate(
            symbol="BTC/USDT",
            rate=-0.01,
            timestamp=datetime.now(UTC),
        )
        assert fr.rate == -0.01


class TestOpenInterestModel:
    def test_valid_open_interest(self):
        oi = OpenInterest(
            symbol="BTC/USDT",
            value=1_000_000.0,
            currency="USDT",
            timestamp=datetime.now(UTC),
            exchange="dry_run_stub",
        )
        assert oi.symbol == "BTC/USDT"
        assert oi.value == 1_000_000.0
        assert oi.currency == "USDT"

    def test_open_interest_defaults(self):
        oi = OpenInterest(
            symbol="ETH/USDT",
            value=500_000.0,
            timestamp=datetime.now(UTC),
        )
        assert oi.currency == "USDT"
        assert oi.exchange == "dry_run_stub"

    def test_open_interest_requires_symbol(self):
        with pytest.raises(Exception):
            OpenInterest(value=1000000, timestamp=datetime.now(UTC))

    def test_open_interest_requires_value(self):
        with pytest.raises(Exception):
            OpenInterest(symbol="BTC/USDT", timestamp=datetime.now(UTC))


class TestDerivativesSignalModel:
    def test_signal_with_both_data(self):
        now = datetime.now(UTC)
        fr = FundingRate(symbol="BTC/USDT", rate=0.01, timestamp=now)
        oi = OpenInterest(symbol="BTC/USDT", value=1_000_000.0, timestamp=now)
        sig = DerivativesSignal(
            symbol="BTC/USDT",
            funding_rate=fr,
            open_interest=oi,
            timestamp=now,
        )
        assert sig.symbol == "BTC/USDT"
        assert sig.funding_rate is not None
        assert sig.open_interest is not None
        assert sig.funding_rate.rate == 0.01
        assert sig.open_interest.value == 1_000_000.0

    def test_signal_with_funding_rate_only(self):
        now = datetime.now(UTC)
        fr = FundingRate(symbol="BTC/USDT", rate=0.01, timestamp=now)
        sig = DerivativesSignal(
            symbol="BTC/USDT",
            funding_rate=fr,
            timestamp=now,
        )
        assert sig.funding_rate is not None
        assert sig.open_interest is None

    def test_signal_with_open_interest_only(self):
        now = datetime.now(UTC)
        oi = OpenInterest(symbol="BTC/USDT", value=1_000_000.0, timestamp=now)
        sig = DerivativesSignal(
            symbol="BTC/USDT",
            open_interest=oi,
            timestamp=now,
        )
        assert sig.funding_rate is None
        assert sig.open_interest is not None

    def test_signal_can_execute_always_false(self):
        sig = DerivativesSignal(
            symbol="BTC/USDT",
            timestamp=datetime.now(UTC),
        )
        assert sig.can_execute is False

    def test_signal_dry_run_only_always_true(self):
        sig = DerivativesSignal(
            symbol="BTC/USDT",
            timestamp=datetime.now(UTC),
        )
        assert sig.dry_run_only is True

    def test_signal_forbids_can_execute_true(self):
        """Type system enforces Literal[False] — can_execute cannot be True."""
        # Pydantic should reject can_execute=True since the type is Literal[False]
        with pytest.raises(Exception):
            DerivativesSignal(
                symbol="BTC/USDT",
                timestamp=datetime.now(UTC),
                can_execute=True,
            )

    def test_signal_forbids_dry_run_only_false(self):
        """Type system enforces Literal[True] — dry_run_only cannot be False."""
        with pytest.raises(Exception):
            DerivativesSignal(
                symbol="BTC/USDT",
                timestamp=datetime.now(UTC),
                dry_run_only=False,
            )

    def test_signal_source_default(self):
        sig = DerivativesSignal(
            symbol="BTC/USDT",
            timestamp=datetime.now(UTC),
        )
        assert sig.source == "derivatives_adapter_dry_run"


# ---------------------------------------------------------------------------
# DryRunDerivativesFetcher tests
# ---------------------------------------------------------------------------

class TestDryRunFetcherFeatureFlag:
    def test_feature_flag_defaults_to_false(self):
        fetcher = DryRunDerivativesFetcher()
        assert fetcher.ENABLED is False

    def test_feature_flag_can_be_enabled(self):
        # We need to create a subclass or instance with ENABLED=True
        # since ENABLED is a class attribute
        class EnabledFetcher(DryRunDerivativesFetcher):
            ENABLED = True

        fetcher = EnabledFetcher()
        assert fetcher.ENABLED is True


class TestDryRunFetcherDisabled:
    def test_get_funding_rate_returns_none_when_disabled(self):
        fetcher = DryRunDerivativesFetcher()
        result = _run(fetcher.get_funding_rate("BTC/USDT"))
        assert result is None

    def test_get_open_interest_returns_none_when_disabled(self):
        fetcher = DryRunDerivativesFetcher()
        result = _run(fetcher.get_open_interest("BTC/USDT"))
        assert result is None


class TestDryRunFetcherEnabled:
    def test_get_funding_rate_returns_stub_data_when_enabled(self):
        class EnabledFetcher(DryRunDerivativesFetcher):
            ENABLED = True

        fetcher = EnabledFetcher()
        result = _run(fetcher.get_funding_rate("BTC/USDT"))
        assert result is not None
        assert result.symbol == "BTC/USDT"
        assert result.rate == 0.01
        assert result.exchange == "dry_run_stub"

    def test_get_open_interest_returns_stub_data_when_enabled(self):
        class EnabledFetcher(DryRunDerivativesFetcher):
            ENABLED = True

        fetcher = EnabledFetcher()
        result = _run(fetcher.get_open_interest("BTC/USDT"))
        assert result is not None
        assert result.symbol == "BTC/USDT"
        assert result.value == 1_000_000.0
        assert result.currency == "USDT"
        assert result.exchange == "dry_run_stub"


class TestDryRunFetcherNeverRaises:
    def test_get_funding_rate_never_raises(self):
        fetcher = DryRunDerivativesFetcher()
        # Even with weird input, should not raise
        result = _run(fetcher.get_funding_rate(""))
        assert result is None

    def test_get_open_interest_never_raises(self):
        fetcher = DryRunDerivativesFetcher()
        result = _run(fetcher.get_open_interest(""))
        assert result is None


class TestDryRunFetcherLogsStubUsage:
    def test_logs_stub_usage_when_enabled(self, caplog):
        class EnabledFetcher(DryRunDerivativesFetcher):
            ENABLED = True

        fetcher = EnabledFetcher()
        with caplog.at_level(logging.INFO, logger="adapters.derivatives.client"):
            _run(fetcher.get_funding_rate("BTC/USDT"))
            _run(fetcher.get_open_interest("ETH/USDT"))

        # Check that stub usage is logged
        assert any("STUB" in record.message for record in caplog.records)
        assert any("DRY-RUN ONLY" in record.message for record in caplog.records)

    def test_logs_disabled_when_disabled(self, caplog):
        fetcher = DryRunDerivativesFetcher()
        with caplog.at_level(logging.DEBUG, logger="adapters.derivatives.client"):
            _run(fetcher.get_funding_rate("BTC/USDT"))

        assert any("ENABLED=False" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# DerivativesAdapter tests
# ---------------------------------------------------------------------------

class TestDerivativesAdapterDisabled:
    def test_returns_none_when_fetcher_disabled(self):
        fetcher = DryRunDerivativesFetcher()
        adapter = DerivativesAdapter(fetcher)
        result = _run(adapter.fetch_and_summarize("BTC/USDT"))
        assert result is None


class TestDerivativesAdapterEnabled:
    def test_returns_signal_when_fetcher_enabled(self):
        class EnabledFetcher(DryRunDerivativesFetcher):
            ENABLED = True

        fetcher = EnabledFetcher()
        adapter = DerivativesAdapter(fetcher)
        result = _run(adapter.fetch_and_summarize("BTC/USDT"))
        assert result is not None
        assert isinstance(result, DerivativesSignal)
        assert result.symbol == "BTC/USDT"
        assert result.can_execute is False
        assert result.dry_run_only is True

    def test_signal_contains_funding_rate(self):
        class EnabledFetcher(DryRunDerivativesFetcher):
            ENABLED = True

        fetcher = EnabledFetcher()
        adapter = DerivativesAdapter(fetcher)
        result = _run(adapter.fetch_and_summarize("BTC/USDT"))
        assert result is not None
        assert result.funding_rate is not None
        assert result.funding_rate.rate == 0.01

    def test_signal_contains_open_interest(self):
        class EnabledFetcher(DryRunDerivativesFetcher):
            ENABLED = True

        fetcher = EnabledFetcher()
        adapter = DerivativesAdapter(fetcher)
        result = _run(adapter.fetch_and_summarize("BTC/USDT"))
        assert result is not None
        assert result.open_interest is not None
        assert result.open_interest.value == 1_000_000.0


class TestDerivativesAdapterNeverRaises:
    def test_adapter_never_raises(self):
        fetcher = DryRunDerivativesFetcher()
        adapter = DerivativesAdapter(fetcher)
        # Even with weird input, should not raise
        result = _run(adapter.fetch_and_summarize(""))
        assert result is None


class TestDerivativesAdapterLogging:
    def test_adapter_logs_stub_usage(self, caplog):
        class EnabledFetcher(DryRunDerivativesFetcher):
            ENABLED = True

        fetcher = EnabledFetcher()
        adapter = DerivativesAdapter(fetcher)
        with caplog.at_level(logging.INFO, logger="adapters.derivatives.adapter"):
            _run(adapter.fetch_and_summarize("BTC/USDT"))

        assert any("DRY-RUN ONLY" in record.message for record in caplog.records)

    def test_adapter_logs_disabled(self, caplog):
        fetcher = DryRunDerivativesFetcher()
        adapter = DerivativesAdapter(fetcher)
        with caplog.at_level(logging.DEBUG, logger="adapters.derivatives.adapter"):
            _run(adapter.fetch_and_summarize("BTC/USDT"))

        assert any("ENABLED=False" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# No network calls verification
# ---------------------------------------------------------------------------

class TestNoNetworkCalls:
    def test_get_funding_rate_makes_no_http_calls(self):
        """Verify no HTTP library is called during funding rate fetch."""
        class EnabledFetcher(DryRunDerivativesFetcher):
            ENABLED = True

        fetcher = EnabledFetcher()
        with patch("urllib.request.urlopen", side_effect=AssertionError("HTTP call detected!")):
            with patch("requests.get", side_effect=AssertionError("HTTP call detected!")):
                result = _run(fetcher.get_funding_rate("BTC/USDT"))
                # Should succeed with stub data, no HTTP calls
                assert result is not None
                assert result.rate == 0.01

    def test_get_open_interest_makes_no_http_calls(self):
        """Verify no HTTP library is called during open interest fetch."""
        class EnabledFetcher(DryRunDerivativesFetcher):
            ENABLED = True

        fetcher = EnabledFetcher()
        with patch("urllib.request.urlopen", side_effect=AssertionError("HTTP call detected!")):
            with patch("requests.get", side_effect=AssertionError("HTTP call detected!")):
                result = _run(fetcher.get_open_interest("BTC/USDT"))
                assert result is not None
                assert result.value == 1_000_000.0

    def test_adapter_makes_no_http_calls(self):
        """Verify adapter makes no HTTP calls."""
        class EnabledFetcher(DryRunDerivativesFetcher):
            ENABLED = True

        fetcher = EnabledFetcher()
        adapter = DerivativesAdapter(fetcher)
        with patch("urllib.request.urlopen", side_effect=AssertionError("HTTP call detected!")):
            with patch("requests.get", side_effect=AssertionError("HTTP call detected!")):
                result = _run(adapter.fetch_and_summarize("BTC/USDT"))
                assert result is not None
