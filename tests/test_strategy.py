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
    s = Strategy(sentiment_weight=1.0)
    ta = {"signal": "BUY", "strength": 5, "indicators": {}}
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


def test_negative_sentiment_reduces_buy_confidence():
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


def test_sell_positive_sentiment_reduces_confidence():
    s = Strategy()
    ta = {"signal": "SELL", "strength": 70, "indicators": {}}
    sentiment = {"score": 0.8, "confidence": 0.9}
    result = s.decide(ta, sentiment, "BTC/USDT", 65000.0, 0.1)
    assert result.action == "SELL"
    assert result.confidence < 70


def test_sell_negative_sentiment_increases_confidence():
    s = Strategy()
    ta = {"signal": "SELL", "strength": 70, "indicators": {}}
    sentiment = {"score": -0.8, "confidence": 0.9}
    result = s.decide(ta, sentiment, "BTC/USDT", 65000.0, 0.1)
    assert result.action == "SELL"
    assert result.confidence > 70
    assert result.confidence <= 100


def test_hold_remains_hold_with_extreme_sentiment():
    s = Strategy(sentiment_weight=5.0)
    ta = {"signal": "HOLD", "strength": 50, "indicators": {}}
    sentiment = {"score": 1.0, "confidence": 1.0}
    result = s.decide(ta, sentiment, "BTC/USDT", 65000.0, 0.1)
    assert result.action == "HOLD"


def test_sell_confidence_clamped_at_0():
    s = Strategy(sentiment_weight=1.0)
    ta = {"signal": "SELL", "strength": 5, "indicators": {}}
    sentiment = {"score": 1.0, "confidence": 1.0}
    result = s.decide(ta, sentiment, "BTC/USDT", 65000.0, 0.1)
    assert result.confidence == 0


def test_sell_confidence_clamped_at_100():
    s = Strategy(sentiment_weight=1.0)
    ta = {"signal": "SELL", "strength": 80, "indicators": {}}
    sentiment = {"score": -1.0, "confidence": 1.0}
    result = s.decide(ta, sentiment, "BTC/USDT", 65000.0, 0.1)
    assert result.confidence == 100


def test_default_sentiment_weight():
    s = Strategy()
    assert s.sentiment_weight == 0.3


def test_market_context_can_increase_confidence():
    s = Strategy(sentiment_weight=0.0)
    ta = {"signal": "BUY", "strength": 60, "indicators": {}}
    sentiment = {"score": 0.0, "confidence": 0.0}
    market_context = {
        "risk_off": False,
        "confidence_adjustment": 6,
        "feed_health": {"is_healthy": True},
    }
    result = s.decide(ta, sentiment, "BTC/USDT", 65000.0, 0.1, market_context=market_context)
    assert result.action == "BUY"
    assert result.confidence == 66


def test_unhealthy_feed_forces_hold():
    s = Strategy()
    ta = {"signal": "BUY", "strength": 80, "indicators": {}}
    sentiment = {"score": 0.5, "confidence": 0.5}
    market_context = {
        "risk_off": True,
        "confidence_adjustment": -20,
        "feed_health": {"is_healthy": False},
    }
    result = s.decide(ta, sentiment, "BTC/USDT", 65000.0, 0.1, market_context=market_context)
    assert result.action == "HOLD"
    assert result.quantity == 0
