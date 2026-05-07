# core/technical.py
import logging

import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import MACD, EMAIndicator
from ta.volatility import BollingerBands

log = logging.getLogger(__name__)


class TechnicalAnalyzer:
    def analyze(self, df: pd.DataFrame) -> dict:
        if len(df) < 50:
            raise ValueError("mindestens 50 Kerzen benötigt")
        close = df["close"]

        rsi = RSIIndicator(close=close, window=14).rsi()
        macd_obj = MACD(close=close, window_slow=26, window_fast=12, window_sign=9)
        ema_50 = EMAIndicator(close=close, window=50).ema_indicator()
        ema_200 = EMAIndicator(close=close, window=200).ema_indicator()
        bb = BollingerBands(close=close, window=20, window_dev=2)

        rsi_val = rsi.iloc[-1]
        macd_val = macd_obj.macd().iloc[-1]
        macd_signal = macd_obj.macd_signal().iloc[-1]
        macd_hist = macd_obj.macd_diff().iloc[-1]
        ema50 = ema_50.iloc[-1]
        ema200 = ema_200.iloc[-1] if len(df) >= 200 else None
        bb_upper = bb.bollinger_hband().iloc[-1]
        bb_lower = bb.bollinger_lband().iloc[-1]
        price = close.iloc[-1]

        score = 0
        if rsi_val < 30:
            score += 30
        elif rsi_val < 45:
            score += 15
        elif rsi_val > 70:
            score -= 30
        elif rsi_val > 55:
            score -= 15

        if macd_val > 0:
            if macd_hist > 0:
                score += 25
            elif macd_hist < 0:
                score -= 10
        else:
            if macd_hist < 0:
                score -= 25
            elif macd_hist > 0:
                score += 5

        if ema200 is not None:
            if price > ema50 > ema200:
                score += 20
            elif price < ema50 < ema200:
                score -= 20
        elif price > ema50:
            score += 10
        elif price < ema50:
            score -= 10

        if price <= bb_lower:
            score += 15
        elif price >= bb_upper:
            score -= 15

        strength = max(0, min(100, 50 + score))
        signal = "BUY" if strength > 65 else ("SELL" if strength < 35 else "HOLD")

        return {
            "signal": signal,
            "strength": strength,
            "indicators": {
                "rsi": round(rsi_val, 2),
                "macd": round(macd_val, 4),
                "macd_signal": round(macd_signal, 4),
                "macd_hist": round(macd_hist, 4),
                "ema_50": round(ema50, 2),
                "ema_200": round(ema200, 2) if ema200 else None,
                "bollinger": {
                    "upper": round(bb_upper, 2),
                    "lower": round(bb_lower, 2),
                },
                "price": round(price, 2),
            },
        }
