"""Tests für FeaturePipeline und PredictiveEngine."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import numpy as np
import pandas as pd
import pytest

from core.feature_pipeline import FeaturePipeline
from core.predictive import PredictiveEngine


def _make_ohlcv(rows: int = 50) -> pd.DataFrame:
    """Erstelle OHLCV-DataFrame mit DatetimeIndex für Tests."""
    dates = [datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=i) for i in range(rows)]
    np.random.seed(42)
    close = 40000 + np.cumsum(np.random.randn(rows) * 100)
    return pd.DataFrame(
        {
            "open": close - np.random.rand(rows) * 50,
            "high": close + np.abs(np.random.randn(rows)) * 80,
            "low": close - np.abs(np.random.randn(rows)) * 80,
            "close": close,
            "volume": np.random.randint(100, 1000, rows).astype(float),
        },
        index=pd.DatetimeIndex(dates),
    )


class TestFeaturePipelineBuildFeatures:
    """Tests für FeaturePipeline.build_features()."""

    def test_build_features_expected_columns(self):
        """Alle erwarteten Feature-Spalten werden erstellt."""
        pipeline = FeaturePipeline()
        ohlcv = _make_ohlcv(50)
        result = pipeline.build_features(ohlcv)

        expected_columns = {
            "returns_1h",
            "returns_4h",
            "returns_24h",
            "log_returns",
            "volatility_20",
            "volatility_50",
            "rsi_14",
            "hour_sin",
            "hour_cos",
            "day_of_week_sin",
            "day_of_week_cos",
            "vwap",
        }

        assert expected_columns.issubset(result.columns)
        assert len(result) == 50

    def test_cyclical_encoding_range(self):
        """Cyclical Encodings liegen im Range [-1, 1]."""
        pipeline = FeaturePipeline()
        ohlcv = _make_ohlcv(50)
        result = pipeline.build_features(ohlcv)

        # Prüfe dass alle Werte im gültigen Range liegen
        assert result["hour_sin"].min() >= -1.0
        assert result["hour_sin"].max() <= 1.0
        assert result["hour_cos"].min() >= -1.0
        assert result["hour_cos"].max() <= 1.0
        assert result["day_of_week_sin"].min() >= -1.0
        assert result["day_of_week_sin"].max() <= 1.0
        assert result["day_of_week_cos"].min() >= -1.0
        assert result["day_of_week_cos"].max() <= 1.0

    def test_empty_dataframe_returns_empty(self):
        """Leerer DataFrame → leerer DataFrame."""
        pipeline = FeaturePipeline()
        empty = pd.DataFrame()
        result = pipeline.build_features(empty)

        assert result.empty

    def test_single_row_dataframe(self):
        """Single-row DataFrame — returns 1 row, NaN for multi-period features."""
        pipeline = FeaturePipeline()
        ohlcv = _make_ohlcv(1)
        result = pipeline.build_features(ohlcv)

        assert len(result) == 1
        assert "returns_1h" in result.columns
        assert "returns_4h" in result.columns

    def test_nan_values_in_close(self):
        """NaN in close column — pipeline should still produce output without crashing."""
        pipeline = FeaturePipeline()
        ohlcv = _make_ohlcv(50)
        ohlcv.loc[ohlcv.index[10], "close"] = np.nan
        ohlcv.loc[ohlcv.index[20], "volume"] = np.nan

        result = pipeline.build_features(ohlcv)

        assert len(result) == 50
        assert "rsi_14" in result.columns


class TestFeaturePipelineAddFearGreed:
    """Tests für FeaturePipeline.add_fear_greed()."""

    @pytest.mark.anyio
    async def test_fear_greed_graceful_on_network_error(self):
        """Bei Netzwerkfehlern wird graceful degradation ausgeführt."""
        pipeline = FeaturePipeline()
        features = _make_ohlcv(5)
        features = pipeline.build_features(features)

        with patch(
            "httpx.AsyncClient.get",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("fail"),
        ):
            result = await pipeline.add_fear_greed(features)

        assert result["fear_greed_value"].iloc[0] is None
        assert result["fear_greed_class"].iloc[0] is None

    @pytest.mark.anyio
    async def test_fear_greed_graceful_on_http_error(self):
        """Bei HTTP-Fehlern (4xx, 5xx) wird graceful degradation ausgeführt."""
        pipeline = FeaturePipeline()
        features = _make_ohlcv(5)
        features = pipeline.build_features(features)

        mock_response = AsyncMock()
        mock_response.raise_for_status = lambda: (_ for _ in ()).throw(httpx.HTTPStatusClientError("404"))

        with patch("httpx.AsyncClient.get", return_value=mock_response):
            result = await pipeline.add_fear_greed(features)

        assert result["fear_greed_value"].iloc[0] is None


class TestPredictiveEnginePredict:
    """Tests für PredictiveEngine.predict()."""

    @patch("core.predictive.MODEL_DIR", Path("/tmp/nonexistent_model_dir_ai4trade"))
    def test_predict_returns_none_without_model(self):
        """Ohne Modell-Datei → None."""
        engine = PredictiveEngine()
        features = _make_ohlcv(50)
        features = FeaturePipeline().build_features(features)

        result = engine.predict(features)

        assert result is None

    def test_predict_returns_dict_with_model(self):
        """Mit Modell-Datei → dict mit direction und confidence."""
        engine = PredictiveEngine()
        features = _make_ohlcv(50)
        features = FeaturePipeline().build_features(features)

        result = engine.predict(features)

        if result is not None:
            assert "direction" in result
            assert "confidence" in result
            assert "model" in result
            assert 0.0 <= result["confidence"] <= 1.0

    def test_predict_returns_none_on_empty_features(self):
        """Leerer DataFrame → None."""
        engine = PredictiveEngine()
        empty_features = pd.DataFrame()

        result = engine.predict(empty_features)

        assert result is None

    def test_predict_returns_none_on_missing_xgboost(self):
        """Wenn xgboost nicht installiert ist → None."""
        engine = PredictiveEngine()
        features = _make_ohlcv(50)
        features = FeaturePipeline().build_features(features)

        with patch.dict("sys.modules", {"xgboost": None}):
            result = engine.predict(features)

        assert result is None
