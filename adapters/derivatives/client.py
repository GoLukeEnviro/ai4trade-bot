"""Derivatives data fetcher protocol and dry-run implementation.

This module defines the DerivativesDataFetcher protocol (abstract interface)
and provides DryRunDerivativesFetcher as the only implementation.

SAFETY:
  - DryRunDerivativesFetcher.ENABLED defaults to False
  - When ENABLED is False, all methods return None
  - When ENABLED is True, methods return static stub data — no network calls
  - No method ever raises an exception
  - No real HTTP calls, no exchange SDK imports
"""

from __future__ import annotations

import abc
import logging
from datetime import UTC, datetime

from adapters.derivatives.models import FundingRate, OpenInterest

log = logging.getLogger(__name__)


class DerivativesDataFetcher(abc.ABC):
    """Abstract protocol for fetching derivatives data.

    All implementations MUST:
      - Return None on any error, never raise
      - Never make real HTTP calls or import exchange SDKs in this scaffold
    """

    @abc.abstractmethod
    async def get_funding_rate(self, symbol: str) -> FundingRate | None:
        """Fetch current funding rate for *symbol*.

        Returns None if unavailable or on any error.
        """

    @abc.abstractmethod
    async def get_open_interest(self, symbol: str) -> OpenInterest | None:
        """Fetch current open interest for *symbol*.

        Returns None if unavailable or on any error.
        """


class DryRunDerivativesFetcher(DerivativesDataFetcher):
    """Dry-run-only derivatives data fetcher.

    Returns static stub data when ENABLED is True and None otherwise.
    Feature flag ENABLED defaults to False — must be explicitly enabled.

    This class makes NO network calls. All data is hardcoded stub values
    suitable for integration testing only.
    """

    ENABLED: bool = False

    # Stub constants
    _STUB_FUNDING_RATE: float = 0.01
    _STUB_OPEN_INTEREST_VALUE: float = 1_000_000.0
    _STUB_EXCHANGE: str = "dry_run_stub"
    _STUB_CURRENCY: str = "USDT"

    async def get_funding_rate(self, symbol: str) -> FundingRate | None:
        """Return stub funding rate when enabled, None otherwise.

        Never raises. Logs stub usage when enabled.
        """
        try:
            if not self.ENABLED:
                log.debug(
                    "DryRunDerivativesFetcher: ENABLED=False, returning None "
                    "for get_funding_rate(%s)",
                    symbol,
                )
                return None

            now = datetime.now(UTC)
            log.info(
                "DryRunDerivativesFetcher: returning STUB funding rate "
                "for symbol=%s rate=%.6f (DRY-RUN ONLY, not real data)",
                symbol,
                self._STUB_FUNDING_RATE,
            )
            return FundingRate(
                symbol=symbol,
                rate=self._STUB_FUNDING_RATE,
                timestamp=now,
                next_funding_time=None,
                exchange=self._STUB_EXCHANGE,
            )
        except Exception as exc:  # noqa: BLE001
            log.error(
                "DryRunDerivativesFetcher.get_funding_rate error for "
                "symbol=%s: %s",
                symbol,
                exc,
            )
            return None

    async def get_open_interest(self, symbol: str) -> OpenInterest | None:
        """Return stub open interest when enabled, None otherwise.

        Never raises. Logs stub usage when enabled.
        """
        try:
            if not self.ENABLED:
                log.debug(
                    "DryRunDerivativesFetcher: ENABLED=False, returning None "
                    "for get_open_interest(%s)",
                    symbol,
                )
                return None

            now = datetime.now(UTC)
            log.info(
                "DryRunDerivativesFetcher: returning STUB open interest "
                "for symbol=%s value=%.2f (DRY-RUN ONLY, not real data)",
                symbol,
                self._STUB_OPEN_INTEREST_VALUE,
            )
            return OpenInterest(
                symbol=symbol,
                value=self._STUB_OPEN_INTEREST_VALUE,
                currency=self._STUB_CURRENCY,
                timestamp=now,
                exchange=self._STUB_EXCHANGE,
            )
        except Exception as exc:  # noqa: BLE001
            log.error(
                "DryRunDerivativesFetcher.get_open_interest error for "
                "symbol=%s: %s",
                symbol,
                exc,
            )
            return None
