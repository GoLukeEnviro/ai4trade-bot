# core/signal_model.py
import time
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Signal:
    pair: str
    action: str  # BUY, SELL, HOLD
    confidence: int  # 0-100
    price: float
    quantity: float
    timestamp: float = 0.0
    mode: str = "dry_run"

    def __post_init__(self):
        if self.timestamp == 0.0:
            object.__setattr__(self, "timestamp", time.time())
        object.__setattr__(self, "mode", "dry_run")

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Intent:
    intent: str
    pair: str | None
    requires_approval: bool
    mode: str = "dry_run"

    def __post_init__(self):
        object.__setattr__(self, "mode", "dry_run")

    def to_dict(self) -> dict:
        return asdict(self)
