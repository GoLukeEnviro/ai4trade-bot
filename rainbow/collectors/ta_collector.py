from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import MACD, EMAIndicator
from ta.volatility import BollingerBands

from rainbow.collectors.base import BaseCollector
from rainbow.exceptions import CollectorError
from rainbow.models.signal import CryptoSignal, Direction, SignalType

log = logging.getLogger(__name__)

# --- RSI-Schwellenwerte ---
RSI_OVERSOLD = 30  # Starker Bullen-Impuls bei Ueberverkauft
RSI_OVERBOUGHT = 70  # Starker Baeren-Impuls bei Ueberkauft
RSI_WEAK_BEAR = 55  # Leicht baerisch oberhalb dieser Schwelle
RSI_WEAK_BULL = 45  # Leicht bullisch unterhalb dieser Schwelle

# --- MACD-Scoring ---
MACD_BULL_SIGNAL_BOOST = 25  # MACD ueber Signal + Histogram positiv
MACD_BEAR_SIGNAL_BOOST = 25  # MACD unter Signal + Histogram negativ
MACD_BULL_DECAY = 10  # MACD positiv aber Histogram negativ (Momentum schwindet)
MACD_BULL_REVERSAL = 5  # MACD negativ aber Histogram positiv (Wende nach oben)

# --- EMA-Trend-Scoring ---
EMA_STRONG_BULL_BOOST = 20  # Preis > EMA50 > EMA200 (starker Aufwaertstrend)
EMA_STRONG_BEAR_BOOST = 20  # Preis < EMA50 < EMA200 (starker Abwaertstrend)
EMA_MILD_BULL_BOOST = 10  # Preis > EMA50 (ohne EMA200-Bestaetigung)
EMA_MILD_BEAR_BOOST = 10  # Preis < EMA50 (ohne EMA200-Bestaetigung)

# --- Bollinger-Band-Scoring ---
BB_OVERSOLD_BOOST = 15  # Preis an unterem Band = potenzieller Long-Einstieg
BB_OVERBOUGHT_BOOST = 15  # Preis an oberem Band = potenzieller Short-Einstieg

# --- Basis- und Schwellenwerte ---
BASE_STRENGTH = 50  # Neutraler Startwert
BUY_THRESHOLD = 65  # Ueberhalb = Kaufsignal
SELL_THRESHOLD = 35  # Unterhalb = Verkaufssignal

_MIN_CANDLES = 50


@runtime_checkable
class MarketDataProvider(Protocol):
    async def get_ohlcv(self, asset: str, timeframe: str, limit: int = 200) -> pd.DataFrame: ...


class TACollector(BaseCollector):
    def __init__(
        self,
        provider: MarketDataProvider,
        assets: list[str],
        timeframes: list[str] | None = None,
    ):
        self._provider = provider
        self._assets = assets
        self._timeframes = timeframes or ["1h"]

    @property
    def name(self) -> str:
        return "ta"

    async def collect(self) -> list[CryptoSignal]:
        signals: list[CryptoSignal] = []
        for asset in self._assets:
            for tf in self._timeframes:
                try:
                    signal = await self._analyze_asset(asset, tf)
                    if signal:
                        signals.append(signal)
                except CollectorError:
                    raise
                except Exception as exc:
                    raise CollectorError(self.name, f"Analyse fehlgeschlagen fuer {asset}/{tf}: {exc}") from exc
        return signals

    async def _analyze_asset(self, asset: str, timeframe: str) -> CryptoSignal | None:
        df = await self._provider.get_ohlcv(asset, timeframe, limit=200)
        if len(df) < _MIN_CANDLES:
            raise CollectorError(self.name, f"Mindestens {_MIN_CANDLES} Kerzen erforderlich, got {len(df)}")

        analysis = self._compute_indicators(df)
        strength = self._score_indicators(analysis)

        signal_label = self._direction_label(strength)
        direction = self._map_direction(signal_label)
        price = float(df["close"].iloc[-1])
        timestamp = datetime.now(UTC)

        return CryptoSignal(
            source=f"ta_{timeframe}",
            asset=asset,
            signal_type=SignalType.TECHNICAL,
            direction=direction,
            strength=round(strength / 100.0, 3),
            confidence=round(strength / 100.0, 3),
            value=price,
            raw_data=self._raw_indicators(analysis),
            metadata={"timeframe": timeframe, "pair": asset},
            timestamp=timestamp,
        )

    def _compute_indicators(self, df: pd.DataFrame) -> dict:
        close = df["close"]

        rsi = RSIIndicator(close=close, window=14).rsi()
        macd_obj = MACD(close=close, window_slow=26, window_fast=12, window_sign=9)
        ema_50 = EMAIndicator(close=close, window=50).ema_indicator()
        ema_200 = EMAIndicator(close=close, window=200).ema_indicator()
        bb = BollingerBands(close=close, window=20, window_dev=2)

        price = float(close.iloc[-1])
        ema200_val = float(ema_200.iloc[-1]) if len(df) >= 200 else None

        return {
            "rsi": float(rsi.iloc[-1]),
            "macd": float(macd_obj.macd().iloc[-1]),
            "macd_signal": float(macd_obj.macd_signal().iloc[-1]),
            "macd_hist": float(macd_obj.macd_diff().iloc[-1]),
            "ema_50": float(ema_50.iloc[-1]),
            "ema_200": ema200_val,
            "bb_upper": float(bb.bollinger_hband().iloc[-1]),
            "bb_lower": float(bb.bollinger_lband().iloc[-1]),
            "price": price,
        }

    def _score_indicators(self, ind: dict) -> float:
        score = 0
        price = ind["price"]
        rsi = ind["rsi"]
        macd = ind["macd"]
        macd_hist = ind["macd_hist"]
        ema50 = ind["ema_50"]
        ema200 = ind["ema_200"]
        bb_upper = ind["bb_upper"]
        bb_lower = ind["bb_lower"]

        # RSI
        if rsi < RSI_OVERSOLD:
            score += RSI_OVERSOLD
        elif rsi < RSI_WEAK_BULL:
            score += int(RSI_OVERSOLD / 2)
        elif rsi > RSI_OVERBOUGHT:
            score -= RSI_OVERBOUGHT - RSI_WEAK_BEAR + RSI_WEAK_BEAR  # -30
        elif rsi > RSI_WEAK_BEAR:
            score -= 15

        # MACD
        if macd > 0:
            if macd_hist > 0:
                score += MACD_BULL_SIGNAL_BOOST
            else:
                score -= MACD_BULL_DECAY
        else:
            if macd_hist < 0:
                score -= MACD_BEAR_SIGNAL_BOOST
            else:
                score += MACD_BULL_REVERSAL

        # EMA
        if ema200 is not None:
            if price > ema50 > ema200:
                score += EMA_STRONG_BULL_BOOST
            elif price < ema50 < ema200:
                score -= EMA_STRONG_BEAR_BOOST
        elif price > ema50:
            score += EMA_MILD_BULL_BOOST
        elif price < ema50:
            score -= EMA_MILD_BEAR_BOOST

        # Bollinger Bands
        if price <= bb_lower:
            score += BB_OVERSOLD_BOOST
        elif price >= bb_upper:
            score -= BB_OVERBOUGHT_BOOST

        return max(0.0, min(100.0, BASE_STRENGTH + score))

    @staticmethod
    def _direction_label(strength: float) -> str:
        if strength > BUY_THRESHOLD:
            return "BUY"
        if strength < SELL_THRESHOLD:
            return "SELL"
        return "HOLD"

    @staticmethod
    def _map_direction(label: str) -> Direction:
        return {
            "BUY": Direction.BULLISH,
            "SELL": Direction.BEARISH,
        }.get(label, Direction.NEUTRAL)

    @staticmethod
    def _raw_indicators(ind: dict) -> dict:
        return {
            "rsi": round(ind["rsi"], 2),
            "macd": round(ind["macd"], 4),
            "macd_signal": round(ind["macd_signal"], 4),
            "macd_hist": round(ind["macd_hist"], 4),
            "ema_50": round(ind["ema_50"], 2),
            "ema_200": round(ind["ema_200"], 2) if ind["ema_200"] is not None else None,
            "bollinger": {
                "upper": round(ind["bb_upper"], 2),
                "lower": round(ind["bb_lower"], 2),
            },
            "price": round(ind["price"], 2),
        }
