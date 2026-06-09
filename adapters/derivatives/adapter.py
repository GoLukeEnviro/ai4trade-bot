"""Derivatives adapter — wraps a DerivativesDataFetcher and produces DerivativesSignal.

This module provides DerivativesAdapter, which is the main entry point for
consuming derivatives data (funding rate + open interest) and producing a
combined DerivativesSignal.

Safety guarantees:
  - Never raises; returns None on any error
  - Checks feature flag before doing anything
  - can_execute is always False in the signal
  - dry_run_only is always True in the signal
  - Logs all operations
  - No network calls, no exchange SDK imports
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from adapters.derivatives.client import DryRunDerivativesFetcher
from adapters.derivatives.models import DerivativesSignal

log = logging.getLogger(__name__)


class DerivativesAdapter:
    """Adapter that wraps a DerivativesDataFetcher and produces DerivativesSignal.

    Parameters
    ----------
    fetcher : DryRunDerivativesFetcher
        The data fetcher to use. Must be a DryRunDerivativesFetcher
        (the only implementation in this scaffold).
    """

    def __init__(self, fetcher: DryRunDerivativesFetcher) -> None:
        self._fetcher = fetcher

    async def fetch_and_summarize(self, symbol: str) -> DerivativesSignal | None:
        """Fetch funding rate and open interest, return combined signal.

        Returns None when:
          - Feature flag is disabled (default)
          - Both data fetches return None
          - Any unexpected error occurs

        Never raises. Logs all outcomes.
        """
        try:
            if not self._fetcher.ENABLED:
                log.debug(
                    "DerivativesAdapter: fetcher ENABLED=False, skipping "
                    "fetch_and_summarize(%s)",
                    symbol,
                )
                return None

            log.info(
                "DerivativesAdapter: fetching derivatives data for %s "
                "(DRY-RUN ONLY)",
                symbol,
            )

            funding_rate = await self._fetcher.get_funding_rate(symbol)
            open_interest = await self._fetcher.get_open_interest(symbol)

            if funding_rate is None and open_interest is None:
                log.warning(
                    "DerivativesAdapter: both funding rate and open interest "
                    "are None for symbol=%s — returning None",
                    symbol,
                )
                return None

            now = datetime.now(UTC)
            signal = DerivativesSignal(
                symbol=symbol,
                funding_rate=funding_rate,
                open_interest=open_interest,
                timestamp=now,
            )

            log.info(
                "DerivativesAdapter: produced DerivativesSignal for %s "
                "funding_rate=%s open_interest=%s (DRY-RUN ONLY)",
                symbol,
                funding_rate is not None,
                open_interest is not None,
            )

            return signal

        except Exception as exc:  # noqa: BLE001
            log.error(
                "DerivativesAdapter.fetch_and_summarize error for "
                "symbol=%s: %s",
                symbol,
                exc,
            )
            return None
