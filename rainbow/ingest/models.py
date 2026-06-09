"""Typed request/response models for the Rainbow signal ingest endpoint."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class RainbowIngestRequest(BaseModel):
    """Incoming signal data posted by external systems.

    Required fields capture the minimum viable signal.  Optional fields
    allow richer enrichment without breaking backward compatibility.
    """

    # --- Required ---
    asset: str = Field(..., min_length=1, description="Trading pair, e.g. 'BTC/USDT'")
    direction: str = Field(..., description="'bullish', 'bearish', or 'neutral'")
    strength: float = Field(..., ge=0.0, le=1.0, description="Signal strength 0.0–1.0")
    source: str = Field(..., min_length=1, description="Origin identifier, e.g. 'rainbow:ta'")
    timestamp: str = Field(..., min_length=1, description="ISO-8601 UTC timestamp")

    # --- Optional ---
    rainbow_score: float | None = Field(default=None, ge=0.0, le=1.0)
    raw_data: dict | None = None
    signal_class: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("direction")
    @classmethod
    def _validate_direction(cls, v: str) -> str:
        allowed = {"bullish", "bearish", "neutral"}
        if v.lower() not in allowed:
            raise ValueError(f"direction must be one of {sorted(allowed)}, got '{v}'")
        return v.lower()

    @field_validator("asset")
    @classmethod
    def _validate_asset(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("asset must be a non-empty string after stripping whitespace")
        return stripped


class RainbowIngestResult(BaseModel):
    """Response returned after an ingest attempt."""

    status: Literal["accepted", "rejected", "error"]
    signal_id: str | None = None
    reason: str = ""
    envelope_created: bool = False
