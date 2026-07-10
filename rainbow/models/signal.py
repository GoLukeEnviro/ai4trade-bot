from datetime import UTC, datetime
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from rainbow.evaluation.models import AIEvaluation


class SignalType(str, Enum):
    TECHNICAL = "technical"
    SENTIMENT = "sentiment"
    NEWS = "news"
    ONCHAIN = "onchain"
    PREDICTION_MARKET = "prediction_market"
    MACRO = "macro"
    SOCIAL = "social"


class Direction(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class CryptoSignal(BaseModel):
    signal_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=_utcnow)
    source: str
    asset: str
    signal_type: SignalType
    direction: Direction | None = None
    strength: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    value: float | None = None
    raw_data: dict | None = None
    metadata: dict = Field(default_factory=dict)
    rainbow_score: float | None = Field(default=None, ge=0.0, le=1.0)
    ai_evaluation: AIEvaluation | None = None
    # Optional fields for enhanced evaluator context (Issue #34)
    timeframe: str | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    leverage: float | None = None

    @model_validator(mode="after")
    def _attach_canonical_symbol(self) -> "CryptoSignal":
        """Attach the canonical Trading-Hub symbol for configured assets."""
        from rainbow.symbols import canonical_symbol_for_asset

        try:
            self.metadata.setdefault("canonical_symbol", canonical_symbol_for_asset(self.asset))
        except ValueError:
            pass
        return self
