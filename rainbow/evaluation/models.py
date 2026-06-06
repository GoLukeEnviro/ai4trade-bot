from typing import Literal

from pydantic import BaseModel, Field


class AIEvaluation(BaseModel):
    ai_confidence: float = Field(..., ge=0.0, le=1.0)
    risk_level: Literal["low", "medium", "high"]
    market_regime: Literal["trending", "ranging", "volatile", "quiet"]
    reasoning: str = Field(..., max_length=300)
    model_used: str
    evaluation_latency_ms: int
