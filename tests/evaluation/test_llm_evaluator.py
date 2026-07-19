"""Tests for the LLM evaluator (updated for Issue #23 — JSON validation & fallback)."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from rainbow.evaluation.llm_evaluator import (
    LLMEvaluator,
    _parse_llm_json,
    _safe_default_evaluation,
)
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


def _mock_raw_response(content: str) -> MagicMock:
    msg = MagicMock()
    msg.content = content
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
        "ai_risk_score": 0.3,
        "signal_quality": "strong",
        "recommended_handling": "summary",
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
    # New fields
    assert result.signal_quality == "strong"
    assert result.recommended_handling == "summary"
    assert result.ai_risk_score == pytest.approx(0.3)


@pytest.mark.anyio
async def test_below_threshold_returns_none(evaluator: LLMEvaluator) -> None:
    result = await evaluator.evaluate(_make_signal(rainbow_score=0.3))
    assert result is None


@pytest.mark.anyio
async def test_timeout_with_fallback_returns_safe_default() -> None:
    """Primary times out, no fallback configured → safe default AIEvaluation."""
    evaluator = LLMEvaluator(
        api_key="sk-test",
        timeout_seconds=0.1,
        threshold=0.5,
    )
    with patch.object(
        evaluator._client.chat.completions,
        "create",
        new_callable=AsyncMock,
        side_effect=asyncio.TimeoutError,
    ):
        result = await evaluator.evaluate(_make_signal(0.9))
    assert result is not None
    assert result.signal_quality == "weak"
    assert result.recommended_handling == "store_only"


@pytest.mark.anyio
async def test_malformed_json_returns_safe_default(evaluator: LLMEvaluator) -> None:
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
    assert result.signal_quality == "weak"
    assert result.recommended_handling == "store_only"


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
async def test_exception_returns_safe_default(evaluator: LLMEvaluator) -> None:
    with patch.object(
        evaluator._client.chat.completions,
        "create",
        new_callable=AsyncMock,
        side_effect=RuntimeError("API error"),
    ):
        result = await evaluator.evaluate(_make_signal(0.9))
    assert result is not None
    assert result.signal_quality == "weak"
    assert result.recommended_handling == "store_only"


# ======================================================================
# Issue #23: JSON validation and fallback tests
# ======================================================================

class TestParseLlmJson:
    def test_valid_json(self):
        parsed = _parse_llm_json('{"ai_confidence": 0.5}')
        assert parsed == {"ai_confidence": 0.5}

    def test_invalid_json_returns_none(self):
        assert _parse_llm_json("not json at all") is None

    def test_json_in_markdown_code_block(self):
        raw = '```json\n{"ai_confidence": 0.8}\n```'
        parsed = _parse_llm_json(raw)
        assert parsed == {"ai_confidence": 0.8}

    def test_json_in_code_block_without_language(self):
        raw = '```\n{"ai_confidence": 0.7}\n```'
        parsed = _parse_llm_json(raw)
        assert parsed == {"ai_confidence": 0.7}

    def test_invalid_json_in_code_block_returns_none(self):
        raw = '```json\n{broken json}\n```'
        assert _parse_llm_json(raw) is None

    def test_non_dict_json_returns_none(self):
        assert _parse_llm_json("[1, 2, 3]") is None

    def test_mixed_text_and_json_code_block(self):
        raw = 'Here is the result:\n```json\n{"ai_confidence": 0.9}\n```\nDone.'
        parsed = _parse_llm_json(raw)
        assert parsed == {"ai_confidence": 0.9}


class TestSafeDefaultEvaluation:
    def test_creates_valid_evaluation(self):
        ev = _safe_default_evaluation("test-model", 100)
        assert ev.ai_confidence == 0.0
        assert ev.signal_quality == "weak"
        assert ev.recommended_handling == "store_only"
        assert ev.model_used == "test-model"
        assert ev.evaluation_latency_ms == 100

    def test_is_valid_ai_evaluation(self):
        from rainbow.evaluation.models import AIEvaluation
        ev = _safe_default_evaluation("m", 0)
        assert isinstance(ev, AIEvaluation)


@pytest.mark.anyio
async def test_fallback_model_on_timeout() -> None:
    """Primary times out, fallback succeeds."""
    call_count = 0

    async def _mock_create(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise TimeoutError()
        # Second call (fallback) succeeds
        msg = MagicMock()
        msg.content = json.dumps({
            "ai_confidence": 0.75,
            "risk_level": "low",
            "market_regime": "trending",
            "reasoning": "Fallback model response.",
        })
        choice = MagicMock()
        choice.message = msg
        resp = MagicMock()
        resp.choices = [choice]
        return resp

    evaluator = LLMEvaluator(
        api_key="sk-test",
        threshold=0.5,
        fallback_model="deepseek-v4-flash",
        timeout_seconds=5.0,
    )
    with patch.object(
        evaluator._client.chat.completions,
        "create",
        new_callable=AsyncMock,
        side_effect=_mock_create,
    ):
        result = await evaluator.evaluate(_make_signal(0.8))

    assert result is not None
    assert result.model_used == "deepseek-v4-flash"
    assert call_count == 2


@pytest.mark.anyio
async def test_fallback_model_also_fails_returns_safe_default() -> None:
    """Both primary and fallback fail → safe default."""
    evaluator = LLMEvaluator(
        api_key="sk-test",
        threshold=0.5,
        fallback_model="deepseek-v4-flash",
        timeout_seconds=5.0,
    )
    with patch.object(
        evaluator._client.chat.completions,
        "create",
        new_callable=AsyncMock,
        side_effect=RuntimeError("Both models fail"),
    ):
        result = await evaluator.evaluate(_make_signal(0.9))

    assert result is not None
    assert result.signal_quality == "weak"
    assert result.recommended_handling == "store_only"


@pytest.mark.anyio
async def test_response_with_extra_text_around_json(evaluator: LLMEvaluator) -> None:
    """LLM returns valid JSON wrapped in extra text — should parse fine."""
    content = (
        'Sure! Here it is:\n'
        '{"ai_confidence": 0.6, "risk_level": "medium",'
        ' "market_regime": "quiet", "reasoning": "test."}\n'
        'Hope that helps!'
    )
    with patch.object(
        evaluator._client.chat.completions,
        "create",
        new_callable=AsyncMock,
        return_value=_mock_raw_response(content),
    ):
        result = await evaluator.evaluate(_make_signal(0.9))
    assert result is not None
    assert result.ai_confidence == pytest.approx(0.6)


@pytest.mark.anyio
async def test_old_format_response_still_works(evaluator: LLMEvaluator) -> None:
    """LLM returns old format (no new fields) — new fields get defaults."""
    payload = {
        "ai_confidence": 0.65,
        "risk_level": "medium",
        "market_regime": "ranging",
        "reasoning": "Neutral outlook.",
    }
    with patch.object(
        evaluator._client.chat.completions,
        "create",
        new_callable=AsyncMock,
        return_value=_mock_response(payload),
    ):
        result = await evaluator.evaluate(_make_signal(0.8))
    assert result is not None
    assert result.signal_quality == "usable"
    assert result.recommended_handling == "store_only"
    assert result.ai_risk_score == pytest.approx(0.5)
