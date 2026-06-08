from typing import Literal

from pydantic import BaseModel, Field


class AIEvaluation(BaseModel):
    ai_confidence: float = Field(..., ge=0.0, le=1.0)
    risk_level: Literal["low", "medium", "high"]
    market_regime: Literal["trending", "ranging", "volatile", "quiet"]
    reasoning: str = Field(..., max_length=300)
    model_used: str
    evaluation_latency_ms: int

    # Extended fields for LLM signal review layer
    ai_risk_score: float = Field(default=0.5, ge=0.0, le=1.0)
    signal_quality: Literal["strong", "usable", "weak", "contradictory"] = "usable"
    recommended_handling: Literal[
        "store_only", "summary", "risk_summary", "review_required", "suppress"
    ] = "store_only"
    contradictions: list[str] = Field(default_factory=list)
    missing_context: list[str] = Field(default_factory=list)
    summary: str = ""
