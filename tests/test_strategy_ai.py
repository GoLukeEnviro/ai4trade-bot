# tests/test_strategy_ai.py
"""Tests for AI evaluation integration in Strategy.decide()."""

from __future__ import annotations

from unittest.mock import MagicMock

from core.ai_evaluator_bridge import AIEvaluatorBridge
from core.signal_model import Signal
from core.strategy import Strategy


def _bullish_ta() -> dict:
    return {"signal": "BUY", "strength": 70, "indicators": {"price": 50000.0}}


def _bearish_ta() -> dict:
    return {"signal": "SELL", "strength": 60, "indicators": {"price": 50000.0}}


def _mock_bridge(ai_confidence: float, risk_level: str) -> AIEvaluatorBridge:
    bridge = AIEvaluatorBridge.__new__(AIEvaluatorBridge)
    bridge._evaluator = MagicMock()
    bridge._enabled = True
    bridge.evaluate = MagicMock(return_value={"ai_confidence": ai_confidence, "risk_level": risk_level})
    return bridge


def test_ai_confidence_reduces_buy_signal() -> None:
    bridge = _mock_bridge(ai_confidence=0.5, risk_level="medium")
    strategy = Strategy(ai_bridge=bridge)
    signal = strategy.decide(_bullish_ta(), {"score": 0.0}, "BTC/USDT", 50000.0, 0.1)
    assert signal.confidence < 70  # Reduced by 0.5 multiplier
    assert signal.action == "BUY"


def test_ai_high_risk_reduces_further() -> None:
    bridge = _mock_bridge(ai_confidence=0.8, risk_level="high")
    strategy = Strategy(ai_bridge=bridge)
    signal = strategy.decide(_bullish_ta(), {"score": 0.0}, "BTC/USDT", 50000.0, 0.1)
    # 70 * 0.8 * 0.8 = 44.8 → 44
    assert signal.confidence <= 45
    assert signal.confidence >= 40


def test_ai_extreme_risk_reduces_hard() -> None:
    bridge = _mock_bridge(ai_confidence=0.8, risk_level="extreme")
    strategy = Strategy(ai_bridge=bridge)
    signal = strategy.decide(_bullish_ta(), {"score": 0.0}, "BTC/USDT", 50000.0, 0.1)
    # 70 * 0.8 * 0.5 = 28
    assert signal.confidence <= 30
    assert signal.confidence >= 20


def test_ai_bridge_disabled_uses_raw_confidence() -> None:
    bridge = _mock_bridge(ai_confidence=0.5, risk_level="medium")
    bridge._enabled = False
    strategy = Strategy(ai_bridge=bridge)
    signal = strategy.decide(_bullish_ta(), {"score": 0.0}, "BTC/USDT", 50000.0, 0.1)
    assert signal.confidence == 70  # No reduction


def test_strategy_without_bridge_uses_raw_confidence() -> None:
    strategy = Strategy()
    signal = strategy.decide(_bullish_ta(), {"score": 0.0}, "BTC/USDT", 50000.0, 0.1)
    assert signal.confidence == 70


def test_ai_does_not_affect_hold() -> None:
    bridge = _mock_bridge(ai_confidence=0.5, risk_level="low")
    strategy = Strategy(ai_bridge=bridge)
    hold_ta = {"signal": "HOLD", "strength": 0, "indicators": {"price": 50000.0}}
    signal = strategy.decide(hold_ta, {"score": 0.0}, "BTC/USDT", 50000.0, 0.1)
    assert signal.action == "HOLD"
    assert signal.confidence == 0


def test_ai_sell_signal() -> None:
    bridge = _mock_bridge(ai_confidence=0.7, risk_level="medium")
    strategy = Strategy(ai_bridge=bridge)
    signal = strategy.decide(_bearish_ta(), {"score": 0.0}, "BTC/USDT", 50000.0, 0.1)
    # 60 * 0.7 = 42
    assert signal.action == "SELL"
    assert signal.confidence == 42
