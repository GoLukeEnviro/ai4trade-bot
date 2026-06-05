import pytest

from rainbow.config.settings import RainbowSettings
from rainbow.models.signal import CryptoSignal, Direction, SignalType


@pytest.fixture
def sample_signal() -> CryptoSignal:
    return CryptoSignal(
        source="ta_rsi_1h",
        asset="BTC",
        signal_type=SignalType.TECHNICAL,
        direction=Direction.BULLISH,
        strength=0.72,
        confidence=0.65,
        value=67.3,
        raw_data={"rsi": 67.3, "macd": 150.2},
        metadata={"timeframe": "1h"},
    )


@pytest.fixture
def settings() -> RainbowSettings:
    return RainbowSettings(
        log_level="DEBUG",
        db_path=":memory:",
        collectors={"ta": {"enabled": True, "interval_seconds": 10}},
    )
