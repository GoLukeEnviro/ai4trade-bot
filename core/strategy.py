# core/strategy.py
import logging

from core.ai_evaluator_bridge import AIEvaluatorBridge
from core.signal_model import Signal

log = logging.getLogger(__name__)

DEFAULT_SENTIMENT_WEIGHT = 0.3


class Strategy:
    def __init__(self, sentiment_weight: float = DEFAULT_SENTIMENT_WEIGHT, ai_bridge: AIEvaluatorBridge | None = None):
        self.sentiment_weight = sentiment_weight
        self._ai_bridge = ai_bridge

    def decide(
        self,
        ta: dict,
        sentiment: dict,
        pair: str,
        price: float,
        quantity: float,
        market_context: dict | None = None,
    ) -> Signal:
        market_context = market_context or {}
        ta_signal = ta["signal"]
        ta_strength = ta["strength"]
        sentiment_score = sentiment.get("score", 0.0)

        if not market_context.get("feed_health", {}).get("is_healthy", True):
            return self._hold(pair, price)

        if market_context.get("risk_off", False):
            return self._hold(pair, price)

        if ta_signal == "HOLD":
            return self._hold(pair, price)

        if ta_signal == "BUY":
            raw = ta_strength * (1 + sentiment_score * self.sentiment_weight)
        else:  # SELL
            raw = ta_strength * (1 - sentiment_score * self.sentiment_weight)

        raw += market_context.get("confidence_adjustment", 0)

        confidence = min(100, max(0, int(raw)))

        # AI evaluation: DeepSeek confidence as multiplier
        signal = Signal(pair=pair, action=ta_signal, confidence=confidence, price=price, quantity=quantity)

        if self._ai_bridge and self._ai_bridge.enabled and confidence >= 1:
            ai_result = self._ai_bridge.evaluate(signal)
            ai_confidence = ai_result["ai_confidence"]
            risk_level = ai_result["risk_level"]

            # Apply AI confidence as multiplier
            confidence = int(confidence * ai_confidence)
            log.info(
                "AI adjusted confidence: %s %s raw=%d × ai_conf=%.2f → %d (risk=%s)",
                pair, ta_signal, raw, ai_confidence, confidence, risk_level,
            )

            # Additional 20% reduction for high risk
            if risk_level == "high":
                confidence = int(confidence * 0.8)
                log.info("Risk reduction (-20%%): %s → confidence=%d", pair, confidence)
            elif risk_level == "extreme":
                confidence = int(confidence * 0.5)
                log.info("Extreme risk reduction (-50%%): %s → confidence=%d", pair, confidence)

            confidence = min(100, max(0, confidence))

        return Signal(pair=pair, action=ta_signal, confidence=confidence, price=price, quantity=quantity)

    @staticmethod
    def _hold(pair: str, price: float) -> Signal:
        return Signal(pair=pair, action="HOLD", confidence=0, price=price, quantity=0)
