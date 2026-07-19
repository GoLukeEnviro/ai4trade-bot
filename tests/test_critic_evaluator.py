"""Tests für CriticEvaluator — Issue #91 (Phase 5: LLM Critic Evaluator)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from rainbow.evaluation.critic_evaluator import (
    CRITIC_SYSTEM_PROMPT,
    TRIGGER_POLICY,
    CriticEvaluator,
    CriticVerdict,
)
from rainbow.evaluation.models import AIEvaluation
from rainbow.models.signal import CryptoSignal, Direction, SignalType

# ======================================================================
# Helpers
# ======================================================================


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


def _make_evaluation(
    risk_level: str = "high",
    ai_risk_score: float = 0.85,
    signal_quality: str = "weak",
    ai_confidence: float = 0.9,
) -> AIEvaluation:
    return AIEvaluation(
        ai_confidence=ai_confidence,
        risk_level=risk_level,  # type: ignore[arg-type]
        market_regime="volatile",
        reasoning="Primary evaluator sees strong bullish momentum.",
        model_used="deepseek-v4-pro",
        evaluation_latency_ms=200,
        ai_risk_score=ai_risk_score,
        signal_quality=signal_quality,  # type: ignore[arg-type]
        recommended_handling="review_required",
        contradictions=["RSI overbought but MACD bullish"],
        missing_context=["No volume data"],
        summary="Strong bullish signal with high risk.",
        warnings=["High leverage environment"],
    )


def _mock_critic_response(payload: dict) -> MagicMock:
    msg = MagicMock()
    msg.content = json.dumps(payload)
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


# ======================================================================
# CriticVerdict Model
# ======================================================================


class TestCriticVerdict:
    def test_default_verdict_not_triggered(self):
        v = CriticVerdict()
        assert v.triggered is False
        assert v.agree_with_primary is True
        assert v.overridden_confidence is None
        assert v.overridden_direction is None

    def test_verdict_with_override(self):
        v = CriticVerdict(
            triggered=True,
            agree_with_primary=False,
            overridden_confidence=0.3,
            overridden_direction="bearish",
            critic_reasoning="Primary overconfident.",
            critic_risk_score=0.9,
            manipulation_suspected=True,
            blind_spots=["No on-chain data"],
            critic_warnings=["Possible wash trading"],
            model_used="deepseek-v4-pro",
            evaluation_latency_ms=150,
        )
        assert v.triggered is True
        assert v.agree_with_primary is False
        assert v.overridden_confidence == 0.3
        assert v.overridden_direction == "bearish"
        assert v.manipulation_suspected is True
        assert "No on-chain data" in v.blind_spots

    def test_confidence_clamped(self):
        # Pydantic validiert Field(ge=0.0, le=1.0) bei Konstruktion —
        # Werte außerhalb des Bereichs werden abgelehnt, nicht geclampt.
        with pytest.raises(Exception):  # ValidationError
            CriticVerdict(overridden_confidence=1.5)
        with pytest.raises(Exception):  # ValidationError
            CriticVerdict(overridden_confidence=-0.5)
        # Innerhalb des Bereichs funktioniert:
        v = CriticVerdict(overridden_confidence=0.0)
        assert v.overridden_confidence == 0.0
        v2 = CriticVerdict(overridden_confidence=1.0)
        assert v2.overridden_confidence == 1.0


# ======================================================================
# Trigger-Policy
# ======================================================================


class TestTriggerPolicy:
    def test_policy_structure(self):
        assert "min_priority" in TRIGGER_POLICY
        assert "min_risk_score" in TRIGGER_POLICY
        assert "signal_quality_triggers" in TRIGGER_POLICY
        assert "high" in TRIGGER_POLICY["min_priority"]
        assert "critical" in TRIGGER_POLICY["min_priority"]
        assert TRIGGER_POLICY["min_risk_score"] == 0.70

    def test_policy_quality_triggers(self):
        assert "contradictory" in TRIGGER_POLICY["signal_quality_triggers"]
        assert "low_confidence_high_risk" in TRIGGER_POLICY["signal_quality_triggers"]


# ======================================================================
# CriticEvaluator — Trigger/No-Trigger-Szenarien
# ======================================================================


class TestCriticTriggerScenarios:
    """Testet, ob der Critic nur bei den richtigen Bedingungen auslöst."""

    @pytest.fixture
    def critic(self, monkeypatch: pytest.MonkeyPatch) -> CriticEvaluator:
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        return CriticEvaluator(enabled=True)

    @pytest.fixture
    def critic_disabled(self, monkeypatch: pytest.MonkeyPatch) -> CriticEvaluator:
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        return CriticEvaluator(enabled=False)

    # --- No-Trigger: disabled ---

    @pytest.mark.asyncio
    async def test_disabled_returns_not_triggered(
        self, critic_disabled: CriticEvaluator,
    ):
        signal = _make_signal()
        evaluation = _make_evaluation(risk_level="high", ai_risk_score=0.9)
        verdict = await critic_disabled.evaluate(signal, evaluation)
        assert verdict.triggered is False

    # --- No-Trigger: low risk ---

    @pytest.mark.asyncio
    async def test_low_risk_not_triggered(self, critic: CriticEvaluator):
        signal = _make_signal()
        evaluation = _make_evaluation(risk_level="low", ai_risk_score=0.3)
        verdict = await critic.evaluate(signal, evaluation)
        assert verdict.triggered is False

    @pytest.mark.asyncio
    async def test_medium_risk_not_triggered(self, critic: CriticEvaluator):
        signal = _make_signal()
        evaluation = _make_evaluation(risk_level="medium", ai_risk_score=0.5)
        verdict = await critic.evaluate(signal, evaluation)
        assert verdict.triggered is False

    # --- No-Trigger: high risk_level aber niedriger risk_score + normale quality ---

    @pytest.mark.asyncio
    async def test_high_risk_low_score_not_triggered(self, critic: CriticEvaluator):
        signal = _make_signal()
        evaluation = _make_evaluation(
            risk_level="high", ai_risk_score=0.5, signal_quality="usable",
        )
        verdict = await critic.evaluate(signal, evaluation)
        assert verdict.triggered is False

    # --- No-Trigger: None primary_evaluation ---

    @pytest.mark.asyncio
    async def test_none_primary_not_triggered(self, critic: CriticEvaluator):
        signal = _make_signal()
        verdict = await critic.evaluate(signal, None)
        assert verdict.triggered is False

    # --- Trigger: high risk + high score ---

    @pytest.mark.asyncio
    async def test_high_risk_high_score_triggers(self, critic: CriticEvaluator):
        signal = _make_signal()
        evaluation = _make_evaluation(risk_level="high", ai_risk_score=0.85)

        with patch.object(critic, "_call_model", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = json.dumps({
                "agree_with_primary": True,
                "overridden_confidence": None,
                "overridden_direction": None,
                "critic_reasoning": "Agree with primary.",
                "critic_risk_score": 0.8,
                "manipulation_suspected": False,
                "blind_spots": [],
                "critic_warnings": [],
            })
            verdict = await critic.evaluate(signal, evaluation)

        assert verdict.triggered is True
        assert verdict.agree_with_primary is True

    # --- Trigger: extreme risk ---

    @pytest.mark.asyncio
    async def test_extreme_risk_triggers(self, critic: CriticEvaluator):
        signal = _make_signal()
        evaluation = _make_evaluation(risk_level="extreme", ai_risk_score=0.95)

        with patch.object(critic, "_call_model", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = json.dumps({
                "agree_with_primary": False,
                "overridden_confidence": 0.2,
                "overridden_direction": "bearish",
                "critic_reasoning": "Primary missed bearish divergence.",
                "critic_risk_score": 0.95,
                "manipulation_suspected": True,
                "blind_spots": ["No funding rate data"],
                "critic_warnings": ["Possible pump and dump"],
            })
            verdict = await critic.evaluate(signal, evaluation)

        assert verdict.triggered is True
        assert verdict.agree_with_primary is False
        assert verdict.overridden_confidence == 0.2
        assert verdict.overridden_direction == "bearish"
        assert verdict.manipulation_suspected is True

    # --- Trigger: quality-based (contradictory) ---

    @pytest.mark.asyncio
    async def test_contradictory_quality_triggers(self, critic: CriticEvaluator):
        signal = _make_signal()
        # high risk_level, aber risk_score unter Schwelle — quality triggert
        evaluation = _make_evaluation(
            risk_level="high", ai_risk_score=0.5, signal_quality="contradictory",
        )

        with patch.object(critic, "_call_model", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = json.dumps({
                "agree_with_primary": False,
                "overridden_confidence": 0.4,
                "overridden_direction": None,
                "critic_reasoning": "Contradictory signals detected.",
                "critic_risk_score": 0.75,
                "manipulation_suspected": False,
                "blind_spots": [],
                "critic_warnings": [],
            })
            verdict = await critic.evaluate(signal, evaluation)

        assert verdict.triggered is True
        assert verdict.agree_with_primary is False


# ======================================================================
# CriticEvaluator — Override-Verhalten
# ======================================================================


class TestCriticOverrides:
    """Testet, dass CriticVerdict confidence und direction überschreiben kann."""

    @pytest.fixture
    def critic(self, monkeypatch: pytest.MonkeyPatch) -> CriticEvaluator:
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        return CriticEvaluator(enabled=True)

    @pytest.mark.asyncio
    async def test_override_confidence(self, critic: CriticEvaluator):
        signal = _make_signal()
        evaluation = _make_evaluation(risk_level="high", ai_risk_score=0.9, ai_confidence=0.95)

        with patch.object(critic, "_call_model", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = json.dumps({
                "agree_with_primary": False,
                "overridden_confidence": 0.35,
                "overridden_direction": None,
                "critic_reasoning": "Confidence too high for available data.",
                "critic_risk_score": 0.88,
                "manipulation_suspected": False,
                "blind_spots": [],
                "critic_warnings": [],
            })
            verdict = await critic.evaluate(signal, evaluation)

        assert verdict.overridden_confidence == 0.35
        assert verdict.overridden_direction is None

    @pytest.mark.asyncio
    async def test_override_direction(self, critic: CriticEvaluator):
        signal = _make_signal(direction=Direction.BULLISH)
        evaluation = _make_evaluation(risk_level="high", ai_risk_score=0.85)

        with patch.object(critic, "_call_model", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = json.dumps({
                "agree_with_primary": False,
                "overridden_confidence": None,
                "overridden_direction": "bearish",
                "critic_reasoning": "Direction contradicts on-chain data.",
                "critic_risk_score": 0.82,
                "manipulation_suspected": False,
                "blind_spots": [],
                "critic_warnings": [],
            })
            verdict = await critic.evaluate(signal, evaluation)

        assert verdict.overridden_direction == "bearish"

    @pytest.mark.asyncio
    async def test_override_both(self, critic: CriticEvaluator):
        signal = _make_signal()
        evaluation = _make_evaluation(risk_level="extreme", ai_risk_score=0.95)

        with patch.object(critic, "_call_model", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = json.dumps({
                "agree_with_primary": False,
                "overridden_confidence": 0.15,
                "overridden_direction": "neutral",
                "critic_reasoning": "Complete disagreement with primary.",
                "critic_risk_score": 0.92,
                "manipulation_suspected": True,
                "blind_spots": ["No order book depth"],
                "critic_warnings": ["Suspicious volume spike"],
            })
            verdict = await critic.evaluate(signal, evaluation)

        assert verdict.overridden_confidence == 0.15
        assert verdict.overridden_direction == "neutral"
        assert verdict.manipulation_suspected is True


# ======================================================================
# CriticEvaluator — Fehlerbehandlung
# ======================================================================


class TestCriticErrorHandling:
    """Testet Timeout, Parse-Fehler und generelle Exceptions."""

    @pytest.fixture
    def critic(self, monkeypatch: pytest.MonkeyPatch) -> CriticEvaluator:
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        return CriticEvaluator(enabled=True, timeout_seconds=0.1)

    @pytest.mark.asyncio
    async def test_timeout_returns_safe_verdict(self, critic: CriticEvaluator):
        import asyncio

        signal = _make_signal()
        evaluation = _make_evaluation(risk_level="high", ai_risk_score=0.9)

        with patch.object(critic, "_call_model", new_callable=AsyncMock) as mock_call:
            mock_call.side_effect = asyncio.TimeoutError
            verdict = await critic.evaluate(signal, evaluation)

        assert verdict.triggered is True
        assert verdict.agree_with_primary is True  # Safe default
        assert "timed out" in verdict.critic_reasoning.lower()

    @pytest.mark.asyncio
    async def test_unparseable_response_returns_safe_verdict(self, critic: CriticEvaluator):
        signal = _make_signal()
        evaluation = _make_evaluation(risk_level="high", ai_risk_score=0.9)

        with patch.object(critic, "_call_model", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = "not valid json at all {{{"
            verdict = await critic.evaluate(signal, evaluation)

        assert verdict.triggered is True
        assert verdict.agree_with_primary is True
        assert "unparseable" in verdict.critic_reasoning.lower()

    @pytest.mark.asyncio
    async def test_generic_exception_returns_safe_verdict(self, critic: CriticEvaluator):
        signal = _make_signal()
        evaluation = _make_evaluation(risk_level="high", ai_risk_score=0.9)

        with patch.object(critic, "_call_model", new_callable=AsyncMock) as mock_call:
            mock_call.side_effect = RuntimeError("Connection refused")
            verdict = await critic.evaluate(signal, evaluation)

        assert verdict.triggered is True
        assert verdict.agree_with_primary is True


# ======================================================================
# CriticEvaluator — Konfiguration
# ======================================================================


class TestCriticConfiguration:
    def test_default_disabled(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        c = CriticEvaluator()
        assert c.enabled is False

    def test_explicit_enabled(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        c = CriticEvaluator(enabled=True)
        assert c.enabled is True

    def test_custom_trigger_config(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        c = CriticEvaluator(
            enabled=True,
            trigger_min_priority=["critical"],
            trigger_min_risk_score=0.85,
            trigger_signal_qualities=["contradictory"],
        )
        assert c._trigger_priorities == frozenset(["critical"])
        assert c._trigger_min_risk_score == 0.85
        assert c._trigger_qualities == frozenset(["contradictory"])


# ======================================================================
# Critic System Prompt
# ======================================================================


class TestCriticSystemPrompt:
    def test_prompt_contains_skeptical_directive(self):
        assert "skeptical" in CRITIC_SYSTEM_PROMPT.lower()

    def test_prompt_contains_manipulation_detection(self):
        assert "manipulation" in CRITIC_SYSTEM_PROMPT.lower()

    def test_prompt_contains_overconfidence_detection(self):
        assert "overconfidence" in CRITIC_SYSTEM_PROMPT.lower()

    def test_prompt_contains_no_fabrication_rule(self):
        assert "never fabricate" in CRITIC_SYSTEM_PROMPT.lower()

    def test_prompt_requires_json_only(self):
        assert "valid json only" in CRITIC_SYSTEM_PROMPT.lower()


# ======================================================================
# Issue #K2 — Graceful degradation bei fehlendem DEEPSEEK_API_KEY
# ======================================================================


class TestCriticMissingApiKey:
    """Bei fehlendem API-Key darf der CriticEvaluator nicht crashen (KeyError).

    Stattdessen: graceful degradation — Konstruktor erzwingt enabled=False,
    evaluate() liefert CriticVerdict(triggered=False).
    """

    def test_constructor_disabled_when_key_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        c = CriticEvaluator(enabled=True)
        # Key fehlt → Konstruktor MUSS deaktivieren, trotz enabled=True
        assert c.enabled is False
        assert c._client is None

    def test_constructor_enabled_when_key_present(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        c = CriticEvaluator(enabled=True)
        assert c.enabled is True
        assert c._client is not None

    def test_constructor_uses_explicit_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        c = CriticEvaluator(enabled=True, api_key="sk-explicit")
        assert c.enabled is True
        assert c._client is not None

    @pytest.mark.anyio
    async def test_evaluate_returns_untriggered_when_disabled(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        c = CriticEvaluator(enabled=True)
        signal = _make_signal()
        evaluation = _make_evaluation()
        verdict = await c.evaluate(signal, evaluation)
        assert verdict.triggered is False
        assert verdict.agree_with_primary is True
