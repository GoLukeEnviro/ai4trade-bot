"""Derivatives data adapter — dry-run-only scaffold.

This package provides a read-only derivatives data fetcher for funding rate
and open interest. It is DRY-RUN-ONLY: no real HTTP calls, no exchange SDK
imports, no order execution, no leverage mutation.

Safety guarantees:
  - Feature flag ENABLED defaults to False
  - All methods return None on error, never raise
  - can_execute is always False
  - dry_run_only is always True
  - No network access whatsoever
"""

from adapters.derivatives.adapter import DerivativesAdapter
from adapters.derivatives.client import DryRunDerivativesFetcher
from adapters.derivatives.models import DerivativesSignal, FundingRate, OpenInterest

__all__ = [
    "DerivativesAdapter",
    "DryRunDerivativesFetcher",
    "DerivativesSignal",
    "FundingRate",
    "OpenInterest",
]
