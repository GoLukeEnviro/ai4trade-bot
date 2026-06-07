# tests/test_technical.py
import pytest

from core.technical import TechnicalAnalyzer
from tests.fixtures.ohlcv_fixtures import make_ohlcv


def test_rsi_calculation():
    df = make_ohlcv(200, 50000, "up")
    ta = TechnicalAnalyzer()
    result = ta.analyze(df)
    assert result["signal"] in ("BUY", "SELL", "HOLD")
    assert "indicators" in result
    assert "rsi" in result["indicators"]
    assert "macd" in result["indicators"]
    assert "ema_50" in result["indicators"]
    assert "ema_200" in result["indicators"]
    assert "bollinger" in result["indicators"]
    assert 0 <= result["strength"] <= 100


def test_uptrend_produces_valid_signal():
    df = make_ohlcv(200, 50000, "up")
    ta = TechnicalAnalyzer()
    result = ta.analyze(df)
    assert result["signal"] in ("BUY", "HOLD")
    assert result["strength"] >= 50


def test_downtrend_produces_valid_signal():
    df = make_ohlcv(200, 50000, "down")
    ta = TechnicalAnalyzer()
    result = ta.analyze(df)
    assert result["signal"] in ("SELL", "HOLD")
    assert result["strength"] <= 50


def test_bollinger_structure():
    df = make_ohlcv(200, 50000)
    ta = TechnicalAnalyzer()
    result = ta.analyze(df)
    bb = result["indicators"]["bollinger"]
    assert "upper" in bb
    assert "lower" in bb
    assert bb["upper"] > bb["lower"]


def test_insufficient_data_raises():
    df = make_ohlcv(10, 50000)
    ta = TechnicalAnalyzer()
    with pytest.raises(ValueError, match="mindestens 50"):
        ta.analyze(df)
