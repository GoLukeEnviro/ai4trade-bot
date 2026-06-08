# core/ai_evaluator_bridge.py
"""Sync wrapper around the async LLMEvaluator for use in the legacy signal pipeline.

Provides graceful fallback when DEEPSEEK_API_KEY is missing or evaluation fails.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.signal_model import Signal

log = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async coroutine from sync context, handling event loop edge cases."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # We're inside an existing event loop — create a new thread
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result(timeout=10)
    else:
        return asyncio.run(coro)


class AIEvaluatorBridge:
    """Synchronous bridge to LLMEvaluator for legacy Strategy integration."""

    def __init__(self, ollama_base_url: str | None = None) -> None:
        self._evaluator = None
        self._enabled = False
        self._ollama_base_url = ollama_base_url
        self._init_evaluator()

    def _init_evaluator(self) -> None:
        """Try to initialize the LLMEvaluator. Graceful fallback if not possible."""
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if api_key:
            try:
                from rainbow.evaluation.llm_evaluator import LLMEvaluator

                model = os.getenv("DEEPSEEK_MODEL", "deepseek-reasoner")
                base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

                self._evaluator = LLMEvaluator(
                    api_key=api_key,
                    base_url=base_url,
                    model=model,
                    timeout_seconds=5.0,
                    threshold=0.3,
                )
                self._enabled = True
                log.info("AI-Bewertung aktiviert (model=%s)", model)
                return
            except Exception as exc:
                log.warning("AI-Bewertung konnte nicht initialisiert werden: %s", exc)

        # Ollama fallback: use when DEEPSEEK_API_KEY not set but OLLAMA_BASE_URL available
        ollama_url = self._ollama_base_url or os.getenv("OLLAMA_BASE_URL", "")
        if ollama_url:
            try:
                from rainbow.evaluation.llm_evaluator import LLMEvaluator

                model = os.getenv("OLLAMA_MODEL", "deepseek-chat")
                # Ollama exposes an OpenAI-compatible API at /v1
                if not ollama_url.endswith("/v1"):
                    base_url = ollama_url.rstrip("/") + "/v1"
                else:
                    base_url = ollama_url

                self._evaluator = LLMEvaluator(
                    api_key="ollama",  # Ollama doesn't need a real key
                    base_url=base_url,
                    model=model,
                    timeout_seconds=10.0,
                    threshold=0.3,
                )
                self._enabled = True
                log.info("AI-Bewertung aktiviert via Ollama (model=%s, url=%s)", model, ollama_url)
                return
            except Exception as exc:
                log.warning("Ollama AI-Bewertung konnte nicht initialisiert werden: %s", exc)

        log.info("DEEPSEEK_API_KEY nicht gesetzt und kein Ollama — AI-Bewertung deaktiviert (graceful fallback)")

    @property
    def enabled(self) -> bool:
        return self._enabled

    def evaluate(self, signal: Signal) -> dict:
        """Evaluate a legacy Signal and return ai_confidence + risk_level.

        Returns:
            dict with keys: ai_confidence (float), risk_level (str)
            On failure: ai_confidence=1.0, risk_level="unknown" (neutral)
        """
        if not self._enabled:
            return {"ai_confidence": 1.0, "risk_level": "unknown"}

        try:
            from rainbow.models.signal import CryptoSignal, Direction, SignalType

            # Map legacy action → Rainbow direction
            direction_map = {"BUY": Direction.BULLISH, "SELL": Direction.BEARISH}
            direction = direction_map.get(signal.action, Direction.NEUTRAL)

            crypto_signal = CryptoSignal(
                source="legacy_strategy",
                asset=signal.pair.replace("/", ""),
                signal_type=SignalType.TECHNICAL,
                direction=direction,
                strength=min(signal.confidence / 100.0, 1.0),
                confidence=min(signal.confidence / 100.0, 1.0),
                value=signal.price,
                raw_data=signal.to_dict(),
            )

            t_start = time.perf_counter()
            result = _run_async(self._evaluator.evaluate(crypto_signal))
            elapsed = time.perf_counter() - t_start

            if result is None:
                log.debug("AI-Bewertung returned None fuer %s (%.2fs)", signal.pair, elapsed)
                return {"ai_confidence": 1.0, "risk_level": "unknown"}

            log.info(
                "AI-Bewertung %s: confidence=%.2f risk=%s (%.0fms)",
                signal.pair,
                result.ai_confidence,
                result.risk_level,
                elapsed * 1000,
            )
            return {
                "ai_confidence": result.ai_confidence,
                "risk_level": result.risk_level,
            }

        except Exception as exc:
            log.warning("AI-Bewertung fehlgeschlagen fuer %s: %s", signal.pair, exc)
            return {"ai_confidence": 1.0, "risk_level": "unknown"}
