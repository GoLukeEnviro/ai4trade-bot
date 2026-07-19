"""Canonical signal envelope — the universal signal container."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


class SignalClass(StrEnum):
    """Broad classification of a signal."""

    ENTRY = "entry"
    EXIT = "exit"
    INVALIDATION = "invalidation"
    RISK = "risk"
    REGIME = "regime"
    SYSTEM_HEALTH = "system_health"
    DATA_QUALITY = "data_quality"


class SignalDirection(StrEnum):
    """Directional bias of a signal."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class SignalPriority(StrEnum):
    """Priority level of a signal."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class DataQualityStatus(StrEnum):
    """Health status of upstream data."""

    OK = "ok"
    DEGRADED = "degraded"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


class Actionability(BaseModel):
    """What actions are permitted for this signal."""

    can_alert: bool
    can_execute: bool = False
    dry_run_only: bool = True

    @model_validator(mode="after")
    def _enforce_safety(self) -> Actionability:
        # can_execute must ALWAYS be False — live execution not yet supported
        object.__setattr__(self, "can_execute", False)
        # dry_run_only must ALWAYS be True
        object.__setattr__(self, "dry_run_only", True)
        return self


class InvalidationRule(BaseModel):
    """When / why a signal should be considered stale or invalidated."""

    max_age_seconds: int = 3600
    conditions: list[str] = []


class DataQuality(BaseModel):
    """Data quality metadata attached to every signal."""

    status: DataQualityStatus
    source_latency_ms: int | None = None
    source_quality: str | None = None
    freshness_seconds: int | None = None


def _utcnow() -> datetime:
    from datetime import UTC

    return datetime.now(UTC)


class CanonicalSignalEnvelope(BaseModel):
    """Universal signal container for the ai4trade-bot ecosystem.

    Every signal produced by any subsystem MUST be wrapped in this envelope
    before it enters the registry, risk gate, or downstream consumers.
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    schema_version: int = 1
    # 'class' shadows builtin — intentional for domain clarity
    signal_class: SignalClass = Field(alias="class")
    subtype: str
    source: str
    asset: str
    timeframe: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    valid_until: datetime | None = None
    direction: SignalDirection
    confidence: float = Field(ge=0.0, le=1.0)
    risk_score: float = Field(ge=0.0, le=1.0)
    priority: SignalPriority = SignalPriority.MEDIUM
    reason_codes: list[str] = Field(default_factory=list)
    features: dict[str, Any] = Field(default_factory=dict)
    data_quality: DataQuality
    actionability: Actionability
    invalidation: InvalidationRule = Field(default_factory=InvalidationRule)
    raw_refs: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}

    @field_validator("confidence")
    @classmethod
    def _validate_confidence(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"confidence must be 0.0–1.0, got {v}")
        return v

    @field_validator("risk_score")
    @classmethod
    def _validate_risk_score(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"risk_score must be 0.0–1.0, got {v}")
        return v
