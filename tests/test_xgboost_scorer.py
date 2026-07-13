"""Tests for the outcome-trained XGBoost signal scorer."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from core.outcomes.model import OutcomeLabel, SignalOutcome
from core.outcomes.repository import OutcomeRepository
from core.signals.envelope import (
    Actionability,
    CanonicalSignalEnvelope,
    DataQuality,
    DataQualityStatus,
    SignalClass,
    SignalDirection,
)
from core.signals.registry import CanonicalSignalRegistry
from rainbow.models.signal import CryptoSignal, Direction, SignalType
from rainbow.processor.scorer import RainbowScorer
from rainbow.processor.xgboost_scorer import FEATURE_COLUMNS, XGBoostSignalScorer
from scripts.train_xgboost import load_training_data


def _envelope(created_at: datetime | None = None) -> CanonicalSignalEnvelope:
    return CanonicalSignalEnvelope(
        id="training-signal",
        signal_class=SignalClass.ENTRY,
        subtype="training",
        source="rainbow:ta",
        asset="BTC/USDT:USDT",
        timeframe="1h",
        created_at=created_at or datetime(2026, 1, 5, 13, tzinfo=UTC),
        direction=SignalDirection.BULLISH,
        confidence=0.75,
        risk_score=0.25,
        features={"rsi_14": 31.0, "funding_rate": -0.0004},
        data_quality=DataQuality(status=DataQualityStatus.OK),
        actionability=Actionability(can_alert=False),
    )


def test_scorer_without_model_file_returns_none(tmp_path) -> None:
    scorer = XGBoostSignalScorer(model_path=tmp_path / "does-not-exist.json")

    assert scorer.score(_envelope()) is None


def test_feature_extraction_provides_every_training_column() -> None:
    features = XGBoostSignalScorer(model_path="missing.json")._extract_features(_envelope())

    assert set(FEATURE_COLUMNS).issubset(features)
    assert features["rsi_14"] == 31.0
    assert features["hour_of_day"] == 13.0
    assert features["day_of_week"] == 0.0


def test_load_training_data_rejects_empty_database(tmp_path) -> None:
    with pytest.raises(ValueError, match="Zu wenig Trainingsdaten: 0"):
        load_training_data(
            db_path=str(tmp_path / "canonical.db"),
            outcomes_db_path=str(tmp_path / "outcomes.db"),
        )


def test_load_training_data_joins_actual_registry_and_outcome_schema(tmp_path) -> None:
    registry = CanonicalSignalRegistry(str(tmp_path / "canonical.db"))
    outcomes = OutcomeRepository(str(tmp_path / "outcomes.db"))
    envelope = _envelope()
    registry.append(envelope)
    outcomes.insert(
        SignalOutcome(
            signal_id=envelope.id,
            asset=envelope.asset,
            direction=envelope.direction.value,
            signal_class=envelope.signal_class.value,
            source=envelope.source,
            emitted_at=envelope.created_at,
            outcome_label=OutcomeLabel.WIN,
            confidence_at_signal=envelope.confidence,
        )
    )

    features, labels = load_training_data(
        db_path=str(tmp_path / "canonical.db"),
        outcomes_db_path=str(tmp_path / "outcomes.db"),
        min_samples=0,
    )

    assert list(features.columns) == FEATURE_COLUMNS
    assert features.loc[0, "rsi_14"] == 31.0
    assert labels.tolist() == [1]
    registry.close()
    outcomes.close()


def test_scorer_loads_saved_dummy_model_and_returns_probability(tmp_path) -> None:
    xgb = pytest.importorskip("xgboost")
    model = xgb.XGBClassifier(n_estimators=1, max_depth=1, random_state=42)
    model.fit([[0.0] * len(FEATURE_COLUMNS), [1.0] * len(FEATURE_COLUMNS)], [0, 1])
    model_path = tmp_path / "scorer.json"
    model.save_model(model_path)

    score = XGBoostSignalScorer(model_path=model_path).score(_envelope())

    assert score is not None
    assert 0.0 <= score <= 1.0


def test_rainbow_scorer_writes_available_ml_score_back_to_signal() -> None:
    class FixedModelScorer:
        def score(self, envelope: CanonicalSignalEnvelope) -> float:
            return 0.91

    signal = CryptoSignal(
        source="test",
        asset="BTC/USDT:USDT",
        signal_type=SignalType.TECHNICAL,
        direction=Direction.BULLISH,
        strength=0.75,
        confidence=0.75,
        metadata={"rsi_14": 31.0},
    )

    result = RainbowScorer(xgboost_scorer=FixedModelScorer()).score([signal])

    assert result[0].rainbow_score == pytest.approx(0.91)
