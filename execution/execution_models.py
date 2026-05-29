from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ExecutionStatus(Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    FILLED = "filled"
    REJECTED = "rejected"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class OrderRequest:
    pair: str
    action: str
    price: float
    quantity: float
    signal_confidence: int
    mode: str = "dry_run"


@dataclass(frozen=True)
class OrderResult:
    request: OrderRequest
    status: ExecutionStatus
    reason: str = ""
    filled_price: float = 0.0
    filled_quantity: float = 0.0
    exchange_order_id: str = ""
