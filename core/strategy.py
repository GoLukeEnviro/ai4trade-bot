# core/strategy.py
import logging

from core.signal_model import Signal

log = logging.getLogger(__name__)

DEFAULT_SENTIMENT_WEIGHT = 0.3


class Strategy:
    def __init__(self, sentiment_weight: float = DEFAULT_SENTIMENT_WEIGHT):
        self.sentiment_weight = sentiment_weight

    def decide(self, ta: dict, sentiment: dict, pair: str, price: float, quantity: float) -> Signal:
        ta_signal = ta["signal"]
        ta_strength = ta["strength"]
        sentiment_score = sentiment.get("score", 0.0)

        if ta_signal == "HOLD":
            return Signal(pair=pair, action="HOLD", confidence=ta_strength, price=price, quantity=0)

        if ta_signal == "BUY":
            raw = ta_strength * (1 + sentiment_score * self.sentiment_weight)
        else:  # SELL
            raw = ta_strength * (1 - sentiment_score * self.sentiment_weight)

        confidence = min(100, max(0, int(raw)))
        return Signal(pair=pair, action=ta_signal, confidence=confidence, price=price, quantity=quantity)
