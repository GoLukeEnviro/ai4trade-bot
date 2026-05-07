# core/strategy.py
import logging

from core.signal_model import Signal

log = logging.getLogger(__name__)


class Strategy:
    def decide(self, ta: dict, sentiment: dict, pair: str, price: float, quantity: float) -> Signal:
        ta_signal = ta["signal"]
        ta_strength = ta["strength"]
        sentiment_score = sentiment.get("score", 0.0)

        if ta_signal == "HOLD":
            return Signal(pair=pair, action="HOLD", confidence=ta_strength, price=price, quantity=0)

        confidence = min(100, max(0, int(ta_strength * (1 + sentiment_score))))
        return Signal(pair=pair, action=ta_signal, confidence=confidence, price=price, quantity=quantity)
