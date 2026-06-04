# core/strategy.py
import logging

from core.signal_model import Signal

log = logging.getLogger(__name__)

DEFAULT_SENTIMENT_WEIGHT = 0.3


class Strategy:
    def __init__(self, sentiment_weight: float = DEFAULT_SENTIMENT_WEIGHT):
        self.sentiment_weight = sentiment_weight

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

        return Signal(pair=pair, action=ta_signal, confidence=confidence, price=price, quantity=quantity)

    @staticmethod
    def _hold(pair: str, price: float) -> Signal:
        return Signal(pair=pair, action="HOLD", confidence=0, price=price, quantity=0)
