"""Price provider abstraction — protocol + implementations.

The outcome evaluator needs price data to judge whether a signal was correct.
This module defines the protocol and provides safe, credential-free implementations.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Protocol

log = logging.getLogger(__name__)


class PriceProvider(Protocol):
    """Protocol for price data providers.

    Implementations must return the price of *asset* at (or nearest to) *at_time*.
    Returns None if price data is unavailable — the evaluator must handle this.
    """

    def get_price(self, asset: str, at_time: datetime) -> float | None: ...


class StaticPriceProvider:
    """Returns a fixed price for any asset.

    Useful for testing and dry-run modes where no live data is available.
    """

    def __init__(self, price_map: dict[str, float] | None = None, default: float = 0.0) -> None:
        self._price_map = price_map or {}
        self._default = default

    def get_price(self, asset: str, at_time: datetime) -> float | None:
        return self._price_map.get(asset, self._default)


class CallbackPriceProvider:
    """Delegates to a callable for maximum flexibility in tests.

    The callback receives (asset, at_time) and must return float | None.
    """

    def __init__(self, callback) -> None:
        self._callback = callback

    def get_price(self, asset: str, at_time: datetime) -> float | None:
        try:
            return self._callback(asset, at_time)
        except Exception as e:
            log.warning("Price callback error for %s: %s", asset, e)
            return None
