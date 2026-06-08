# core/risk_gate.py
"""Risk and Data-Quality Gate — validates signals before routing."""

from __future__ import annotations

import logging

import config
from core.metrics import SIGNALS_BLOCKED
from core.signal_model import Signal

log = logging.getLogger(__name__)


class RiskGate:
    """Validates signals against risk and data-quality rules.

    Rules (all must pass for approval):
        1. Signal confidence >= CONFIDENCE_THRESHOLD
        2. Feed health must be healthy
        3. Market context must not have risk_off == True
        4. Drawdown must not exceed MAX_DOWNDRAW_PCT
    """

    def __init__(
        self,
        confidence_threshold: int | None = None,
        max_drawdown_pct: float | None = None,
    ) -> None:
        self._confidence_threshold = (
            confidence_threshold if confidence_threshold is not None else config.CONFIDENCE_THRESHOLD
        )
        self._max_drawdown_pct = (
            max_drawdown_pct if max_drawdown_pct is not None else getattr(config, "MAX_DOWNDRAW_PCT", 15.0)
        )

    def check(self, signal: Signal, market_context: dict) -> tuple[bool, str]:
        """Check whether a signal should be approved for routing.

        Args:
            signal: The legacy Signal to validate.
            market_context: Dict with keys like feed_health, risk_off, drawdown_pct.

        Returns:
            (approved, reason) — approved=True if signal passes all checks.
        """
        # Rule 1: Confidence threshold
        if signal.confidence < self._confidence_threshold:
            reason = f"confidence {signal.confidence} < threshold {self._confidence_threshold}"
            self._block(signal, reason)
            return False, reason

        # Rule 2: Feed health
        feed_health = market_context.get("feed_health", {})
        if not feed_health.get("is_healthy", True):
            reason = "feed unhealthy"
            self._block(signal, reason)
            return False, reason

        # Rule 3: Risk-off mode
        if market_context.get("risk_off", False):
            reason = "risk_off mode active"
            self._block(signal, reason)
            return False, reason

        # Rule 4: Drawdown
        drawdown = market_context.get("drawdown_pct", 0.0)
        if drawdown > self._max_drawdown_pct:
            reason = f"drawdown {drawdown:.1f}% > max {self._max_drawdown_pct:.1f}%"
            self._block(signal, reason)
            return False, reason

        return True, "approved"

    def _block(self, signal: Signal, reason: str) -> None:
        """Log warning and increment blocked counter."""
        log.warning("Signal blocked: %s %s — %s", signal.pair, signal.action, reason)
        SIGNALS_BLOCKED.labels(pair=signal.pair, reason=reason).inc()
