from typing import Literal

from pydantic import BaseModel, Field


class AIEvaluation(BaseModel):
    ai_confidence: float = Field(..., ge=0.0, le=1.0)
    risk_level: Literal["low", "medium", "high", "extreme"]
    market_regime: str
    reasoning: str = Field(..., max_length=500)
    model_used: str
    evaluation_latency_ms: int

    # Extended fields (Issue #4 — institutional-grade evaluation layer)
    signal_id: str | None = None
    strength: str | None = None
    expected_holding_period: str | None = None
    key_takeaways: list[str] = Field(default_factory=list)
    supporting_factors: list[str] = Field(default_factory=list)
    conflicting_factors: list[str] = Field(default_factory=list)
    invalidations: list[str] = Field(default_factory=list)
    recommended_action: str | None = None
    suggested_position_size_pct: float | None = Field(default=None, ge=0.0, le=100.0)
    suggested_leverage: float | None = Field(default=None, ge=1.0, le=125.0)
    stop_loss_review: str | None = None
    take_profit_review: str | None = None
    risk_reward_assessment: str | None = None
    data_completeness_score: float | None = Field(default=None, ge=0.0, le=1.0)
    warnings: list[str] = Field(default_factory=list)
    timeframe: str | None = None
