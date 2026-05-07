# tests/test_strategy.py
from core.strategy import Strategy
from core.signal_model import Signal


def test_bullish_ta_with_positive_sentiment():
    s = Strategy()
    ta = {"signal": "BUY", "strength": 75, "indicators": {}}
    sentiment = {"score": 0.8, "confidence": 0.9}
    result = s.decide(ta, sentiment, "BTC/USDT", 65000.0, 0.1)
    assert result.action == "BUY"
    assert result.confidence > 75
    assert result.confidence <= 100


def test_confidence_clamped_at_100():
    s = Strategy()
    ta = {"signal": "BUY", "strength": 100, "indicators": {}}
    sentiment = {"score": 1.0, "confidence": 1.0}
    result = s.decide(ta, sentiment, "BTC/USDT", 65000.0, 0.1)
    assert result.confidence == 100


def test_confidence_clamped_at_0():
    s = Strategy()
    ta = {"signal": "SELL", "strength": 5, "indicators": {}}
    sentiment = {"score": -1.0, "confidence": 1.0}
    result = s.decide(ta, sentiment, "BTC/USDT", 65000.0, 0.1)
    assert result.confidence == 0


def test_hold_when_ta_is_hold():
    s = Strategy()
    ta = {"signal": "HOLD", "strength": 50, "indicators": {}}
    sentiment = {"score": 1.0, "confidence": 1.0}
    result = s.decide(ta, sentiment, "BTC/USDT", 65000.0, 0.1)
    assert result.action == "HOLD"


def test_sentiment_cannot_trigger_signal():
    s = Strategy()
    ta = {"signal": "HOLD", "strength": 30, "indicators": {}}
    sentiment = {"score": 1.0, "confidence": 1.0}
    result = s.decide(ta, sentiment, "BTC/USDT", 65000.0, 0.1)
    assert result.action == "HOLD"


def test_negative_sentiment_reduces_confidence():
    s = Strategy()
    ta = {"signal": "BUY", "strength": 70, "indicators": {}}
    sentiment = {"score": -0.8, "confidence": 0.9}
    result = s.decide(ta, sentiment, "BTC/USDT", 65000.0, 0.1)
    assert result.action == "BUY"
    assert result.confidence < 70


def test_neutral_sentiment_no_change():
    s = Strategy()
    ta = {"signal": "BUY", "strength": 70, "indicators": {}}
    sentiment = {"score": 0.0, "confidence": 0.0}
    result = s.decide(ta, sentiment, "BTC/USDT", 65000.0, 0.1)
    assert result.confidence == 70


def test_returns_signal_with_dry_run_mode():
    s = Strategy()
    ta = {"signal": "BUY", "strength": 60, "indicators": {}}
    sentiment = {"score": 0.5, "confidence": 0.5}
    result = s.decide(ta, sentiment, "ETH/USDT", 3000.0, 1.5)
    assert isinstance(result, Signal)
    assert result.mode == "dry_run"
    assert result.pair == "ETH/USDT"
    assert result.price == 3000.0
    assert result.quantity == 1.5
