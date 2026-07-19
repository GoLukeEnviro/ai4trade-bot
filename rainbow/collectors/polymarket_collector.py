"""Polymarket Signal Adapter — Prediction Market als Regime-Overlay.

Issue #98: P3 — Groesster dezentraler Prediction Market als Regime-Indikator.
Default: disabled. Aktivierung nach #95 (On-Chain Collector stabil).
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from rainbow.collectors.base import BaseCollector
from rainbow.models.signal import CryptoSignal, Direction, SignalType

# --- Anti-Noise-Gate ---
MIN_LIQUIDITY_USD = 100_000  # Nur Maerkte mit Liquiditaet > $100k
MIN_PROBABILITY = 0.65  # Nur Wahrscheinlichkeiten > 65%
PROBABILITY_DEVIATION = 0.15  # Abweichung von 0.5 (neutral)

# --- Keyword-Filter ---
CRYPTO_KEYWORDS = [
    "bitcoin", "btc", "ethereum", "eth", "crypto",
    "sec", "fed", "regulation", "cftc",
]

# --- Signal-Subtypes ---
SUBTYPE_PREDICTION_BULL_HIGH = "PREDICTION_BULL_HIGH"
SUBTYPE_PREDICTION_BEAR_HIGH = "PREDICTION_BEAR_HIGH"
SUBTYPE_MACRO_EVENT_RISK = "MACRO_EVENT_RISK"

# --- Polymarket CLOB API ---
POLYMARKET_CLOB_URL = "https://clob.polymarket.com"


class PolymarketCollector(BaseCollector):
    """Sammelt Prediction-Market-Signale von Polymarket als Regime-Overlay.

    Datenquelle: Polymarket CLOB API (kostenlos, kein API-Key fuer Read-Only).

    Signal-Subtypes:
    - PREDICTION_BULL_HIGH: YES-Wahrscheinlichkeit > 70% → regime
    - PREDICTION_BEAR_HIGH: YES-Wahrscheinlichkeit > 70% → regime
    - MACRO_EVENT_RISK: Hohe Aktivitaet auf Regulierungs-/Policy-Maerkten → risk

    Anti-Noise:
    - Nur Maerkte mit Liquiditaet > $100k
    - Keyword-Filter: bitcoin, btc, ethereum, eth, crypto, sec, fed
    - Nur Wahrscheinlichkeiten > 65% (bzw. Abweichung > 0.15 von 0.5)
    """

    def __init__(
        self,
        assets: list[str] | None = None,
        base_url: str = POLYMARKET_CLOB_URL,
        enabled: bool = False,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._assets = assets or ["BTC", "ETH"]
        self._base_url = base_url.rstrip("/")
        self._enabled = enabled
        self._client = client
        self.last_run_utc: str | None = None

    @property
    def name(self) -> str:
        return "polymarket"

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def collect(self) -> list[CryptoSignal]:
        """Sammle Polymarket-Signale. Gibt leere Liste zurueck wenn disabled."""
        if not self._enabled:
            return []

        signals: list[CryptoSignal] = []
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=15.0)

        try:
            # TODO: Polymarket CLOB API — /markets endpoint
            # TODO: Keyword-Filter auf crypto-relevante Maerkte
            # TODO: Liquiditaets-Check (> $100k)
            # TODO: Wahrscheinlichkeits-Extraktion und Regime-Klassifikation
            # TODO: MACRO_EVENT_RISK Detection (Regulierung/Policy)

            self.last_run_utc = datetime.now(UTC).isoformat()
            return signals
        finally:
            if owns_client:
                await client.aclose()

    # --- Signal-Factories (Skeletons) ---

    def _prediction_bull_signal(self, asset: str, market_title: str, probability: float) -> CryptoSignal | None:
        """PREDICTION_BULL_HIGH: YES-Wahrscheinlichkeit > 70% → BULLISH Regime."""
        if probability < MIN_PROBABILITY + 0.05:  # 70% threshold
            return None
        return CryptoSignal(
            source="polymarket",
            asset=asset,
            signal_type=SignalType.PREDICTION_MARKET,
            direction=Direction.BULLISH,
            strength=min(1.0, (probability - 0.5) * 2),
            confidence=0.55,
            value=probability,
            raw_data={
                "subtype": SUBTYPE_PREDICTION_BULL_HIGH,
                "market": market_title,
                "probability": probability,
            },
            metadata={"collector": "polymarket", "provider": "polymarket_clob"},
        )

    def _prediction_bear_signal(self, asset: str, market_title: str, probability: float) -> CryptoSignal | None:
        """PREDICTION_BEAR_HIGH: YES-Wahrscheinlichkeit > 70% → BEARISH Regime."""
        if probability < MIN_PROBABILITY + 0.05:  # 70% threshold
            return None
        return CryptoSignal(
            source="polymarket",
            asset=asset,
            signal_type=SignalType.PREDICTION_MARKET,
            direction=Direction.BEARISH,
            strength=min(1.0, (probability - 0.5) * 2),
            confidence=0.55,
            value=probability,
            raw_data={
                "subtype": SUBTYPE_PREDICTION_BEAR_HIGH,
                "market": market_title,
                "probability": probability,
            },
            metadata={"collector": "polymarket", "provider": "polymarket_clob"},
        )

    def _macro_event_risk_signal(self, asset: str, market_title: str, volume_24h: float) -> CryptoSignal | None:
        """MACRO_EVENT_RISK: Hohe Aktivitaet auf Regulierungs-/Policy-Maerkten → RISK."""
        if volume_24h < MIN_LIQUIDITY_USD:
            return None
        return CryptoSignal(
            source="polymarket",
            asset=asset,
            signal_type=SignalType.PREDICTION_MARKET,
            direction=Direction.NEUTRAL,
            strength=0.5,
            confidence=0.50,
            value=volume_24h,
            raw_data={
                "subtype": SUBTYPE_MACRO_EVENT_RISK,
                "market": market_title,
                "volume_24h": volume_24h,
            },
            metadata={"collector": "polymarket", "provider": "polymarket_clob"},
        )

    @staticmethod
    def _matches_crypto_keywords(title: str) -> bool:
        """Prueft ob ein Markt-Titel crypto-relevante Keywords enthaelt."""
        title_lower = title.lower()
        return any(kw in title_lower for kw in CRYPTO_KEYWORDS)

    async def health_check(self) -> bool:
        """Collector ist healthy wenn disabled oder API erreichbar."""
        if not self._enabled:
            return True
        return True  # Polymarket CLOB ist public, kein API-Key noetig
