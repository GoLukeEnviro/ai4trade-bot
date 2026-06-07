from datetime import datetime

import pytest
from pydantic import ValidationError

from rainbow.config.settings import (
    ApiConfig,
    CollectorConfig,
    RainbowSettings,
    ScorerConfig,
)
from rainbow.exceptions import CollectorError, ConfigValidationError, ProviderError, RainbowError
from rainbow.models.signal import CryptoSignal, Direction, SignalType


class TestCryptoSignal:
    def test_minimal_signal(self):
        sig = CryptoSignal(
            source="ta_rsi_1h",
            asset="BTC",
            signal_type=SignalType.TECHNICAL,
            strength=0.5,
            confidence=0.5,
        )
        assert sig.signal_id
        assert isinstance(sig.timestamp, datetime)
        assert sig.direction is None
        assert sig.value is None
        assert sig.raw_data is None
        assert sig.metadata == {}
        assert sig.rainbow_score is None

    def test_full_signal(self, sample_signal):
        assert sample_signal.source == "ta_rsi_1h"
        assert sample_signal.asset == "BTC"
        assert sample_signal.signal_type == SignalType.TECHNICAL
        assert sample_signal.direction == Direction.BULLISH
        assert sample_signal.strength == 0.72
        assert sample_signal.confidence == 0.65
        assert sample_signal.value == 67.3
        assert sample_signal.raw_data is not None

    def test_strength_out_of_range_high(self):
        with pytest.raises(ValidationError):
            CryptoSignal(
                source="test",
                asset="BTC",
                signal_type=SignalType.TECHNICAL,
                strength=1.5,
                confidence=0.5,
            )

    def test_strength_out_of_range_negative(self):
        with pytest.raises(ValidationError):
            CryptoSignal(
                source="test",
                asset="BTC",
                signal_type=SignalType.TECHNICAL,
                strength=-0.1,
                confidence=0.5,
            )

    def test_confidence_out_of_range(self):
        with pytest.raises(ValidationError):
            CryptoSignal(
                source="test",
                asset="BTC",
                signal_type=SignalType.TECHNICAL,
                strength=0.5,
                confidence=2.0,
            )

    def test_rainbow_score_validation(self):
        with pytest.raises(ValidationError):
            CryptoSignal(
                source="test",
                asset="BTC",
                signal_type=SignalType.TECHNICAL,
                strength=0.5,
                confidence=0.5,
                rainbow_score=1.5,
            )

    def test_signal_type_enum(self):
        assert SignalType.TECHNICAL == "technical"
        assert SignalType.SENTIMENT == "sentiment"
        assert SignalType.ONCHAIN == "onchain"
        assert SignalType.PREDICTION_MARKET == "prediction_market"

    def test_direction_enum(self):
        assert Direction.BULLISH == "bullish"
        assert Direction.BEARISH == "bearish"
        assert Direction.NEUTRAL == "neutral"

    def test_serialization_roundtrip(self, sample_signal):
        data = sample_signal.model_dump()
        restored = CryptoSignal(**data)
        assert restored.source == sample_signal.source
        assert restored.asset == sample_signal.asset
        assert restored.strength == sample_signal.strength

    def test_json_serialization(self, sample_signal):
        json_str = sample_signal.model_dump_json()
        restored = CryptoSignal.model_validate_json(json_str)
        assert restored.source == sample_signal.source

    def test_unique_signal_ids(self):
        sig1 = CryptoSignal(
            source="test",
            asset="BTC",
            signal_type=SignalType.TECHNICAL,
            strength=0.5,
            confidence=0.5,
        )
        sig2 = CryptoSignal(
            source="test",
            asset="BTC",
            signal_type=SignalType.TECHNICAL,
            strength=0.5,
            confidence=0.5,
        )
        assert sig1.signal_id != sig2.signal_id


class TestRainbowSettings:
    def test_defaults(self):
        s = RainbowSettings()
        assert s.log_level == "INFO"
        assert s.api.port == 8000
        assert "ta" in s.collectors

    def test_collector_config_validation(self):
        with pytest.raises(ValidationError):
            CollectorConfig(interval_seconds=5)

    def test_scorer_weights_must_sum_to_one(self):
        with pytest.raises(ValidationError):
            ScorerConfig(weights={"technical": 0.5, "sentiment": 0.3})

    def test_scorer_weights_valid(self):
        s = ScorerConfig(weights={"technical": 0.5, "sentiment": 0.5})
        assert s.weights["technical"] == 0.5

    def test_api_port_range(self):
        with pytest.raises(ValidationError):
            ApiConfig(port=99999)

    def test_from_yaml_missing_file(self, tmp_path):
        s = RainbowSettings.from_yaml(tmp_path / "nonexistent.yml")
        assert s.log_level == "INFO"

    def test_from_yaml_valid_file(self, tmp_path):
        yaml_content = "log_level: DEBUG\napi:\n  port: 9000\n"
        path = tmp_path / "test.yml"
        path.write_text(yaml_content)
        s = RainbowSettings.from_yaml(path)
        assert s.log_level == "DEBUG"
        assert s.api.port == 9000


class TestExceptions:
    def test_collector_error_attributes(self):
        err = CollectorError("ta", "RSI calculation failed")
        assert err.collector_name == "ta"
        assert "ta" in str(err)
        assert isinstance(err, RainbowError)

    def test_provider_error_attributes(self):
        err = ProviderError("bitget", "timeout")
        assert err.provider_name == "bitget"
        assert isinstance(err, RainbowError)

    def test_config_validation_error(self):
        err = ConfigValidationError("bad config")
        assert isinstance(err, RainbowError)
