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
async def test_timeout_returns_none(evaluator: LLMEvaluator) -> None:
    with patch.object(
        evaluator._client.chat.completions,
        "create",
        new_callable=AsyncMock,
        side_effect=asyncio.TimeoutError,
    ):
        result = await evaluator.evaluate(_make_signal(0.9))
    assert result is None


@pytest.mark.anyio
async def test_malformed_json_returns_none(evaluator: LLMEvaluator) -> None:
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
    assert result is None


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
async def test_exception_returns_none(evaluator: LLMEvaluator) -> None:
    with patch.object(
        evaluator._client.chat.completions,
        "create",
        new_callable=AsyncMock,
        side_effect=RuntimeError("API error"),
    ):
        result = await evaluator.evaluate(_make_signal(0.9))
    assert result is None
