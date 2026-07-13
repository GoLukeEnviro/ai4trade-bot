"""Optional, read-only XGBoost inference for canonical signal envelopes."""

from __future__ import annotations

import logging
from datetime import UTC
from pathlib import Path
from typing import Any

import pandas as pd

from core.signals.envelope import CanonicalSignalEnvelope

logger = logging.getLogger(__name__)

FEATURE_COLUMNS = [
    "rsi_14",
    "macd_histogram",
    "bb_width",
    "atr_14",
    "ema_cross_signal",
    "volume_ratio",
    "confidence",
    "risk_score",
    "funding_rate",
    "open_interest_ratio",
    "hour_of_day",
    "day_of_week",
]


class XGBoostSignalScorer:
    """Load a persisted model and return a win probability when available."""

    MODEL_PATH = "models/xgboost_signal_scorer.json"

    def __init__(self, model_path: str | Path = MODEL_PATH) -> None:
        self.model_path = Path(model_path)
        self.model: Any | None = None
        self._load_model()

    def _load_model(self) -> None:
        if not self.model_path.exists():
            return
        try:
            from xgboost import XGBClassifier
        except ImportError:
            logger.warning("XGBoost model found but xgboost is not installed; ML scoring is disabled")
            return
        try:
            model = XGBClassifier()
            model.load_model(self.model_path)
            self.model = model
        except (OSError, ValueError) as exc:
            logger.warning("Could not load XGBoost scorer from %s: %s", self.model_path, exc)

    def score(self, envelope: CanonicalSignalEnvelope) -> float | None:
        """Return model win probability, or ``None`` when no model is available."""
        if self.model is None:
            return None
        frame = pd.DataFrame([self._extract_features(envelope)]).reindex(
            columns=FEATURE_COLUMNS,
            fill_value=0.0,
        )
        probability = self.model.predict_proba(frame)
        return float(probability[0][1])

    def _extract_features(self, envelope: CanonicalSignalEnvelope) -> dict[str, float]:
        """Normalize envelope features into the persisted model's feature schema."""
        values = {column: 0.0 for column in FEATURE_COLUMNS}
        for key, value in (envelope.features or {}).items():
            if key in values and isinstance(value, (int, float)):
                values[key] = float(value)
        created_at = envelope.created_at.astimezone(UTC)
        values.update(
            {
                "confidence": float(envelope.confidence),
                "risk_score": float(envelope.risk_score),
                "hour_of_day": float(created_at.hour),
                "day_of_week": float(created_at.weekday()),
            }
        )
        return values
