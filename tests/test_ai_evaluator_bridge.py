# tests/test_ai_evaluator_bridge.py
"""Tests for core.ai_evaluator_bridge.AIEvaluatorBridge."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

from core.ai_evaluator_bridge import AIEvaluatorBridge
from core.signal_model import Signal


def _make_signal(action: str = "BUY", confidence: int = 75) -> Signal:
    return Signal(pair="BTC/USDT", action=action, confidence=confidence, price=50000.0, quantity=0.1)


def test_bridge_disabled_without_api_key() -> None:
    with patch.dict(os.environ, {}, clear=False):
        # Ensure DEEPSEEK_API_KEY is not set
        os.environ.pop("DEEPSEEK_API_KEY", None)
        bridge = AIEvaluatorBridge()
        assert bridge.enabled is False
        result = bridge.evaluate(_make_signal())
        assert result["ai_confidence"] == 1.0
        assert result["risk_level"] == "unknown"


def test_bridge_disabled_returns_neutral() -> None:
    bridge = AIEvaluatorBridge.__new__(AIEvaluatorBridge)
    bridge._evaluator = None
    bridge._enabled = False
    result = bridge.evaluate(_make_signal())
    assert result["ai_confidence"] == 1.0


def test_bridge_evaluate_with_mock_evaluator() -> None:
    from rainbow.evaluation.models import AIEvaluation

    mock_eval = MagicMock()
    mock_result = AIEvaluation(
        ai_confidence=0.8,
        risk_level="medium",
        market_regime="trending",
        reasoning="Strong uptrend",
        model_used="test",
        evaluation_latency_ms=100,
    )
    mock_eval.evaluate = AsyncMock(return_value=mock_result)

    bridge = AIEvaluatorBridge.__new__(AIEvaluatorBridge)
    bridge._evaluator = mock_eval
    bridge._enabled = True

    result = bridge.evaluate(_make_signal())
    assert result["ai_confidence"] == 0.8
    assert result["risk_level"] == "medium"


def test_bridge_evaluate_exception_returns_neutral() -> None:
    mock_eval = MagicMock()
    mock_eval.evaluate = AsyncMock(side_effect=Exception("API error"))

    bridge = AIEvaluatorBridge.__new__(AIEvaluatorBridge)
    bridge._evaluator = mock_eval
    bridge._enabled = True

    result = bridge.evaluate(_make_signal())
    assert result["ai_confidence"] == 1.0
    assert result["risk_level"] == "unknown"


def test_bridge_evaluate_none_result_returns_neutral() -> None:
    mock_eval = MagicMock()
    mock_eval.evaluate = AsyncMock(return_value=None)

    bridge = AIEvaluatorBridge.__new__(AIEvaluatorBridge)
    bridge._evaluator = mock_eval
    bridge._enabled = True

    result = bridge.evaluate(_make_signal())
    assert result["ai_confidence"] == 1.0
