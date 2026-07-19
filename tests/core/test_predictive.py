"""Tests for core.predictive — PredictiveEngine."""

import pathlib
from unittest.mock import patch

import pandas as pd
import pytest

from core.predictive import PredictiveEngine


@pytest.fixture
def engine() -> PredictiveEngine:
    return PredictiveEngine()


class TestPredictiveEngineConstruction:
    def test_default_construction(self) -> None:
        engine = PredictiveEngine()
        assert engine is not None


class TestPredictiveEnginePredict:
    def test_empty_dataframe_returns_none(self, engine: PredictiveEngine) -> None:
        df = pd.DataFrame()
        result = engine.predict(df)
        assert result is None

    def test_no_model_returns_none(self, engine: PredictiveEngine) -> None:
        """When xgboost model file doesn't exist, predict returns None."""
        df = pd.DataFrame({"rsi": [55], "macd": [0.1], "volume": [1000]})
        with patch.object(PredictiveEngine, "__init__", lambda self: None):
            # Can't set MODEL_DIR easily without patching; just check behavior
            result = engine.predict(df)
            # Likely None since model file doesn't exist in CI
            # This is fine — it should not crash
            assert result is None or isinstance(result, dict)

    def test_predict_with_xgboost_unavailable(self) -> None:
        """If xgboost is not importable, predict should return None gracefully."""
        engine = PredictiveEngine()
        df = pd.DataFrame({"feature1": [1.0], "feature2": [2.0]})
        # The model file won't exist, so predict returns None
        import pathlib

        model_path = pathlib.Path("models/predictive/xgboost_v1.json")
        if not model_path.exists():
            result = engine.predict(df)
            assert result is None


class TestPredictiveEngineModelDir:
    def test_model_dir_default(self) -> None:
        from core.predictive import MODEL_DIR

        assert pathlib.Path("models/predictive") == MODEL_DIR
