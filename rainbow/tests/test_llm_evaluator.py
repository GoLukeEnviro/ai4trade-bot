from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from rainbow.evaluation.llm_evaluator import LLMEvaluator
from rainbow.models.signal import CryptoSignal, Direction, SignalType


def _make_signal(
    rainbow_score: float = 0.8,
    direction: Direction = Direction.BULLISH,
    asset: str = "BTC",
) -> CryptoSignal:
    return CryptoSignal(
        source="test",
        asset=asset,
        signal_type=SignalType.TECHNICAL,
        direction=direction,
        strength=0.75,
        confidence=0.8,
        rainbow_score=rainbow_score,
        raw_data={"rsi": 62, "macd": 0.003},
        timestamp=datetime.now(UTC),
    )


def _mock_response(payload: dict) -> MagicMock:
    msg = MagicMock()
    msg.content = json.dumps(payload)
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


@pytest.fixture
def evaluator(monkeypatch: pytest.MonkeyPatch) -> LLMEvaluator:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    return LLMEvaluator(threshold=0.5)


@pytest.mark.anyio
async def test_successful_evaluation(evaluator: LLMEvaluator) -> None:
    payload = {
        "ai_confidence": 0.82,
        "risk_level": "low",
        "market_regime": "trending",
        "reasoning": "RSI indicates bullish momentum.",
    }
    with patch.object(
        evaluator._client.chat.completions,
        "create",
        new_callable=AsyncMock,
        return_value=_mock_response(payload),
    ):
        result = await evaluator.evaluate(_make_signal(0.8))

    assert result is not None
    assert result.ai_confidence == pytest.approx(0.82)
    assert result.risk_level == "low"
    assert result.market_regime == "trending"
    assert result.model_used == "deepseek-reasoner"
    assert result.evaluation_latency_ms >= 0


@pytest.mark.anyio
async def test_below_threshold_returns_none(evaluator: LLMEvaluator) -> None:
    result = await evaluator.evaluate(_make_signal(rainbow_score=0.3))
    assert result is None


@pytest.mark.anyio
async def test_skip_on_low_score_false_returns_fallback(evaluator: LLMEvaluator) -> None:
    """With skip_on_low_score=False, even low-score signals get evaluated."""
    with patch.object(
        evaluator._client.chat.completions,
        "create",
        new_callable=AsyncMock,
        side_effect=RuntimeError("API error"),
    ):
        result = await evaluator.evaluate(_make_signal(rainbow_score=0.3), skip_on_low_score=False)
    # Returns safe fallback instead of None
    assert result is not None
    assert result.ai_confidence == 0.0
    assert result.risk_level == "extreme"
    assert result.recommended_action == "skip"


@pytest.mark.anyio
async def test_timeout_returns_safe_fallback(evaluator: LLMEvaluator) -> None:
    """Task 5D: timeout returns safe AIEvaluation, not None."""
    with patch.object(
        evaluator._client.chat.completions,
        "create",
        new_callable=AsyncMock,
        side_effect=asyncio.TimeoutError,
    ):
        result = await evaluator.evaluate(_make_signal(0.9))
    assert result is not None
    assert result.ai_confidence == 0.0
    assert result.risk_level == "extreme"
    assert result.recommended_action == "skip"


@pytest.mark.anyio
async def test_malformed_json_returns_safe_fallback(evaluator: LLMEvaluator) -> None:
    """Task 5B: JSONDecodeError returns safe AIEvaluation, not None."""
    bad = MagicMock()
    bad.choices = [MagicMock()]
    bad.choices[0].message.content = "not valid json"
    with patch.object(
        evaluator._client.chat.completions,
        "create",
        new_callable=AsyncMock,
        return_value=bad,
    ):
        result = await evaluator.evaluate(_make_signal(0.9))
    assert result is not None
    assert result.ai_confidence == 0.0
    assert result.risk_level == "extreme"
    assert result.recommended_action == "skip"


@pytest.mark.anyio
async def test_cache_hit_skips_api(evaluator: LLMEvaluator) -> None:
    payload = {
        "ai_confidence": 0.7,
        "risk_level": "medium",
        "market_regime": "ranging",
        "reasoning": "Range-bound market.",
    }
    with patch.object(
        evaluator._client.chat.completions,
        "create",
        new_callable=AsyncMock,
        return_value=_mock_response(payload),
    ) as mock_api:
        signal = _make_signal(0.75)
        await evaluator.evaluate(signal)
        await evaluator.evaluate(signal)
        assert mock_api.call_count == 1


@pytest.mark.anyio
async def test_exception_returns_safe_fallback(evaluator: LLMEvaluator) -> None:
    """Task 5D: exception returns safe AIEvaluation, not None."""
    with patch.object(
        evaluator._client.chat.completions,
        "create",
        new_callable=AsyncMock,
        side_effect=RuntimeError("API error"),
    ):
        result = await evaluator.evaluate(_make_signal(0.9))
    assert result is not None
    assert result.ai_confidence == 0.0
    assert result.risk_level == "extreme"


@pytest.mark.anyio
async def test_successful_evaluation_with_extended_fields(evaluator: LLMEvaluator) -> None:
    """Verify extended AIEvaluation fields are populated from LLM response."""
    payload = {
        "overall_confidence": 0.75,
        "risk_rating": "medium",
        "market_regime_alignment": "bull_trend",
        "reasoning_summary": "Multiple indicators align.",
        "signal_id": "sig-123",
        "strength": "strong",
        "expected_holding_period": "4-8h",
        "key_takeaways": ["RSI bullish", "Volume increasing"],
        "supporting_factors": ["MACD crossover"],
        "conflicting_factors": ["High funding rate"],
        "invalidations": ["Break below 48k"],
        "recommended_action": "enter",
        "suggested_position_size_pct": 5.0,
        "suggested_leverage": 2.0,
        "stop_loss_review": "Below 48500",
        "take_profit_review": "At 52000",
        "risk_reward_assessment": "1:2.5",
        "data_completeness_score": 0.85,
        "warnings": ["Volatility elevated"],
        "timeframe": "1h",
    }
    with patch.object(
        evaluator._client.chat.completions,
        "create",
        new_callable=AsyncMock,
        return_value=_mock_response(payload),
    ):
        result = await evaluator.evaluate(_make_signal(0.8))

    assert result is not None
    assert result.ai_confidence == 0.75
    assert result.risk_level == "medium"
    assert result.market_regime == "bull_trend"
    assert result.signal_id == "sig-123"
    assert result.strength == "strong"
    assert result.key_takeaways == ["RSI bullish", "Volume increasing"]
    assert result.recommended_action == "enter"
    assert result.suggested_position_size_pct == 5.0
    assert result.data_completeness_score == 0.85
    assert result.warnings == ["Volatility elevated"]
    assert result.timeframe == "1h"


@pytest.mark.anyio
async def test_empty_string_response_returns_safe_fallback(evaluator: LLMEvaluator) -> None:
    """Task 5B: empty string response → safe fallback."""
    empty_resp = MagicMock()
    empty_resp.choices = [MagicMock()]
    empty_resp.choices[0].message.content = ""
    with patch.object(
        evaluator._client.chat.completions,
        "create",
        new_callable=AsyncMock,
        return_value=empty_resp,
    ):
        result = await evaluator.evaluate(_make_signal(0.9))
    assert result is not None
    assert result.ai_confidence == 0.0


@pytest.mark.anyio
async def test_partial_json_returns_safe_fallback(evaluator: LLMEvaluator) -> None:
    """Task 5B: partial JSON → JSONDecodeError → safe fallback."""
    partial_resp = MagicMock()
    partial_resp.choices = [MagicMock()]
    partial_resp.choices[0].message.content = '{"ai_confidence": 0.5'
    with patch.object(
        evaluator._client.chat.completions,
        "create",
        new_callable=AsyncMock,
        return_value=partial_resp,
    ):
        result = await evaluator.evaluate(_make_signal(0.9))
    assert result is not None
    assert result.ai_confidence == 0.0
