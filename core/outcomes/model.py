"""Outcome model — typed data for signal evaluation results."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class OutcomeLabel(StrEnum):
    """Label assigned to a signal after evaluation."""

    WIN = "win"
    LOSS = "loss"
    NEUTRAL = "neutral"
    EXPIRED = "expired"
    UNKNOWN = "unknown"


class SignalOutcome(BaseModel):
    """A single outcome record — the result of evaluating a past signal.

    This is purely observational. It never triggers trading, strategy changes,
    or parameter modulation. It exists to build a training-ready dataset.
    """

    signal_id: str
    asset: str
    direction: str  # bullish / bearish / neutral
    signal_class: str  # entry / exit / etc.
    source: str = ""
    emitted_at: datetime
    evaluated_at: datetime = Field(default_factory=lambda: _utcnow())
    evaluation_window_seconds: int = 3600
    entry_price: float | None = None
    outcome_price: float | None = None
    price_change_pct: float | None = None
    expected_direction: str = ""  # bullish / bearish / neutral
    outcome_label: OutcomeLabel = OutcomeLabel.UNKNOWN
    outcome_score: float = Field(default=0.0, ge=-1.0, le=1.0)
    reason: str = ""
    confidence_at_signal: float | None = None
    extra: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def _enforce_safety(self) -> SignalOutcome:
        """Outcome tracking is observational — never triggers execution."""
        return self


def _utcnow() -> datetime:
    from datetime import UTC

    return datetime.now(UTC)
