from datetime import UTC, datetime
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field

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
    timeframe: str | None = None
    stop_loss: float | None = None
    take_profit: float | list[float] | None = None
    leverage: float = Field(default=1.0, ge=1.0, le=125.0)
