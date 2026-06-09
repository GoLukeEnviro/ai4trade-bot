"""Data models for the derivatives adapter — funding rate, open interest, signal summary.

All models are Pydantic BaseModels with strict typing. No network fields,
no exchange credentials, no order/leverage fields.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class FundingRate(BaseModel):
    """Funding rate data for a perpetual futures contract.

    Attributes
    ----------
    symbol : str
        Trading pair symbol (e.g. "BTC/USDT").
    rate : float
        Current funding rate (e.g. 0.01 = 0.01%).
    timestamp : datetime
        When this rate was observed.
    next_funding_time : datetime | None
        When the next funding payment occurs, if known.
    exchange : str
        Exchange identifier (stub value for dry-run).
    """

    symbol: str
    rate: float
    timestamp: datetime
    next_funding_time: datetime | None = None
    exchange: str = "dry_run_stub"


class OpenInterest(BaseModel):
    """Open interest data for a perpetual futures contract.

    Attributes
    ----------
    symbol : str
        Trading pair symbol (e.g. "BTC/USDT").
    value : float
        Open interest value in quote currency units.
    currency : str
        Currency denomination (e.g. "USDT").
    timestamp : datetime
        When this value was observed.
    exchange : str
        Exchange identifier (stub value for dry-run).
    """

    symbol: str
    value: float
    currency: str = "USDT"
    timestamp: datetime
    exchange: str = "dry_run_stub"


class DerivativesSignal(BaseModel):
    """Combined derivatives signal summary.

    Aggregates funding rate and open interest into a single signal
    suitable for downstream consumers (e.g. confidence modulation,
    risk gate, signal envelope).

    Safety invariants:
      - can_execute is always False
      - dry_run_only is always True
      - No order execution fields
      - No leverage fields

    Attributes
    ----------
    symbol : str
        Trading pair symbol.
    funding_rate : FundingRate | None
        Funding rate data, None if unavailable.
    open_interest : OpenInterest | None
        Open interest data, None if unavailable.
    can_execute : Literal[False]
        Always False — no live execution.
    dry_run_only : Literal[True]
        Always True — dry-run-only scaffold.
    source : str
        Source identifier.
    timestamp : datetime
        When this signal was assembled.
    """

    symbol: str
    funding_rate: FundingRate | None = None
    open_interest: OpenInterest | None = None
    can_execute: Literal[False] = False
    dry_run_only: Literal[True] = True
    source: str = "derivatives_adapter_dry_run"
    timestamp: datetime
