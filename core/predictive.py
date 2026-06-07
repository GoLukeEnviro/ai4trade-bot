from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

MODEL_DIR = Path("models/predictive")


class PredictiveEngine:
    """Wrapper for predictive models. Phase 1: XGBoost Classifier (graceful if no model)."""

    def predict(self, features: pd.DataFrame) -> dict[str, Any] | None:
        if features.empty:
            return None

        model_path = MODEL_DIR / "xgboost_v1.json"
        if not model_path.exists():
            logger.debug("No trained model found at %s, skipping prediction", model_path)
            return None

        try:
            import xgboost as xgb

            booster = xgb.Booster()
            booster.load_model(str(model_path))

            feature_cols = [c for c in features.columns if c not in ("fear_greed_class",)]
            last_row = features[feature_cols].iloc[[-1]].fillna(0)
            dmatrix = xgb.DMatrix(last_row)
            proba = booster.predict(dmatrix)[0]

            if isinstance(proba, (list, np.ndarray)):
                confidence = float(max(proba))
                direction_idx = int(proba.index(max(proba))) if isinstance(proba, list) else int(proba.argmax())
                directions = ["DOWN", "FLAT", "UP"]
                direction = directions[direction_idx] if direction_idx < len(directions) else "FLAT"
            else:
                confidence = float(proba)
                direction = "UP" if confidence > 0.5 else "DOWN"

            return {
                "direction": direction,
                "confidence": round(min(1.0, max(0.0, confidence)), 3),
                "model": "xgboost_v1",
                "feature_count": len(feature_cols),
            }
        except ImportError:
            logger.warning("xgboost not installed, prediction unavailable")
            return None
        except Exception as exc:
            logger.warning("Prediction failed: %s", exc)
            return None
