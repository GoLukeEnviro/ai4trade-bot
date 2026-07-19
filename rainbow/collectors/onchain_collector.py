"""On-Chain Collector — Exchange Inflow/Outflow + Whale Transfers (Glassnode/CryptoQuant).

Issue #95: P2 — Dritte unabhaengige Signal-Quelle neben TA und Derivatives.
Default: disabled. Aktivierung nach #90 (Derivatives Collector stabil).
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from rainbow.collectors.base import BaseCollector
from rainbow.models.signal import CryptoSignal, Direction, SignalType

# --- Anti-Noise-Gate ---
WHALE_MIN_VALUE_USD = 5_000_000  # Nur Transfers > $5M
COOLDOWN_SECONDS = 3600  # Max 1 On-Chain-Signal pro Asset pro Stunde
INFLOW_SPIKE_MULTIPLIER = 2.0  # Net-Inflow > 2x 30-Tage-Durchschnitt
SOPR_CAPITULATION_THRESHOLD = 0.97  # SOPR < 0.97 = Kapitulation (bullish Kontraindikator)

# --- Signal-Subtypes ---
SUBTYPE_EXCHANGE_INFLOW_SPIKE = "EXCHANGE_INFLOW_SPIKE"
SUBTYPE_EXCHANGE_OUTFLOW_SPIKE = "EXCHANGE_OUTFLOW_SPIKE"
SUBTYPE_WHALE_TRANSFER_LARGE = "WHALE_TRANSFER_LARGE"
SUBTYPE_SOPR_CAPITULATION = "SOPR_CAPITULATION"
SUBTYPE_STABLECOIN_INFLOW = "STABLECOIN_INFLOW"


class OnChainCollector(BaseCollector):
    """Sammelt On-Chain-Signale von Glassnode, CryptoQuant und Whale Alert.

    Datenquellen (Prioritaet):
    - Glassnode API: Exchange Netflow, SOPR, MVRV, Stablecoin Flow (Freemium)
    - CryptoQuant API: Exchange Inflow/Outflow, Funding Rates, LSR (Freemium)
    - Whale Alert API: Grosse On-Chain Transfers >$5M (1000 req/mo kostenlos)
    - Nansen: Smart Money Wallet Tracking (kostenpflichtig, optional)

    Anti-Noise:
    - Nur Transfers > $5M
    - Signal nur bei Korrelation mit mind. einem anderen Signal (TA oder Derivatives)
    - Cooldown: max 1 On-Chain-Signal pro Asset pro Stunde
    """

    def __init__(
        self,
        assets: list[str] | None = None,
        glassnode_api_key: str | None = None,
        cryptoquant_api_key: str | None = None,
        whale_alert_api_key: str | None = None,
        enabled: bool = False,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._assets = assets or ["BTC", "ETH"]
        self._glassnode_key = glassnode_api_key
        self._cryptoquant_key = cryptoquant_api_key
        self._whale_alert_key = whale_alert_api_key
        self._enabled = enabled
        self._client = client
        self._last_signal_ts: dict[str, datetime] = {}  # asset -> last signal timestamp
        self.last_run_utc: str | None = None

    @property
    def name(self) -> str:
        return "onchain"

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def collect(self) -> list[CryptoSignal]:
        """Sammle On-Chain-Signale. Gibt leere Liste zurueck wenn disabled oder keine API-Keys."""
        if not self._enabled:
            return []

        if not any([self._glassnode_key, self._cryptoquant_key, self._whale_alert_key]):
            return []

        signals: list[CryptoSignal] = []
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=15.0)

        try:
            for asset in self._assets:
                if self._is_cooldown_active(asset):
                    continue

                # TODO: Glassnode Exchange Netflow
                # TODO: CryptoQuant Exchange Inflow/Outflow
                # TODO: Whale Alert Transfers
                # TODO: SOPR Capitulation Detection
                # TODO: Stablecoin Inflow Detection

            self.last_run_utc = datetime.now(UTC).isoformat()
            return signals
        finally:
            if owns_client:
                await client.aclose()

    def _is_cooldown_active(self, asset: str) -> bool:
        """Prueft ob der Cooldown fuer dieses Asset noch aktiv ist."""
        last = self._last_signal_ts.get(asset)
        if last is None:
            return False
        return (datetime.now(UTC) - last).total_seconds() < COOLDOWN_SECONDS

    def _record_signal(self, asset: str) -> None:
        """Vermerkt den Zeitpunkt des letzten Signals fuer Cooldown."""
        self._last_signal_ts[asset] = datetime.now(UTC)

    # --- Signal-Factories (Skeletons) ---

    def _exchange_inflow_signal(self, asset: str, net_inflow: float, avg_30d: float) -> CryptoSignal | None:
        """EXCHANGE_INFLOW_SPIKE: Net-Inflow > 2x 30-Tage-Durchschnitt → BEARISH."""
        if avg_30d <= 0 or net_inflow <= avg_30d * INFLOW_SPIKE_MULTIPLIER:
            return None
        self._record_signal(asset)
        return CryptoSignal(
            source="onchain",
            asset=asset,
            signal_type=SignalType.ONCHAIN,
            direction=Direction.BEARISH,
            strength=min(1.0, net_inflow / (avg_30d * INFLOW_SPIKE_MULTIPLIER)),
            confidence=0.65,
            value=net_inflow,
            raw_data={"subtype": SUBTYPE_EXCHANGE_INFLOW_SPIKE, "net_inflow": net_inflow, "avg_30d": avg_30d},
            metadata={"collector": "onchain", "provider": "glassnode"},
        )

    def _exchange_outflow_signal(self, asset: str, net_outflow: float, avg_30d: float) -> CryptoSignal | None:
        """EXCHANGE_OUTFLOW_SPIKE: Net-Outflow > 2x 30-Tage-Durchschnitt → BULLISH."""
        if avg_30d <= 0 or net_outflow <= avg_30d * INFLOW_SPIKE_MULTIPLIER:
            return None
        self._record_signal(asset)
        return CryptoSignal(
            source="onchain",
            asset=asset,
            signal_type=SignalType.ONCHAIN,
            direction=Direction.BULLISH,
            strength=min(1.0, net_outflow / (avg_30d * INFLOW_SPIKE_MULTIPLIER)),
            confidence=0.65,
            value=net_outflow,
            raw_data={"subtype": SUBTYPE_EXCHANGE_OUTFLOW_SPIKE, "net_outflow": net_outflow, "avg_30d": avg_30d},
            metadata={"collector": "onchain", "provider": "glassnode"},
        )

    def _whale_transfer_signal(self, asset: str, value_usd: float, from_exchange: bool) -> CryptoSignal | None:
        """WHALE_TRANSFER_LARGE: Transfer > $5M auf/von Exchange → NEUTRAL (Risk)."""
        if value_usd < WHALE_MIN_VALUE_USD:
            return None
        self._record_signal(asset)
        return CryptoSignal(
            source="onchain",
            asset=asset,
            signal_type=SignalType.ONCHAIN,
            direction=Direction.NEUTRAL,
            strength=0.5,
            confidence=0.55,
            value=value_usd,
            raw_data={
                "subtype": SUBTYPE_WHALE_TRANSFER_LARGE,
                "value_usd": value_usd,
                "from_exchange": from_exchange,
            },
            metadata={"collector": "onchain", "provider": "whale_alert"},
        )

    def _sopr_capitulation_signal(self, asset: str, sopr: float) -> CryptoSignal | None:
        """SOPR_CAPITULATION: SOPR < 0.97 → BULLISH (Kontraindikator)."""
        if sopr >= SOPR_CAPITULATION_THRESHOLD:
            return None
        self._record_signal(asset)
        return CryptoSignal(
            source="onchain",
            asset=asset,
            signal_type=SignalType.ONCHAIN,
            direction=Direction.BULLISH,
            strength=min(1.0, (SOPR_CAPITULATION_THRESHOLD - sopr) / 0.1 + 0.5),
            confidence=0.60,
            value=sopr,
            raw_data={"subtype": SUBTYPE_SOPR_CAPITULATION, "sopr": sopr},
            metadata={"collector": "onchain", "provider": "glassnode"},
        )

    def _stablecoin_inflow_signal(self, asset: str, inflow_usd: float) -> CryptoSignal | None:
        """STABLECOIN_INFLOW: Stablecoin-Zufluss auf Exchange → BULLISH."""
        if inflow_usd <= 0:
            return None
        self._record_signal(asset)
        return CryptoSignal(
            source="onchain",
            asset=asset,
            signal_type=SignalType.ONCHAIN,
            direction=Direction.BULLISH,
            strength=0.55,
            confidence=0.60,
            value=inflow_usd,
            raw_data={"subtype": SUBTYPE_STABLECOIN_INFLOW, "inflow_usd": inflow_usd},
            metadata={"collector": "onchain", "provider": "glassnode"},
        )

    async def health_check(self) -> bool:
        """Collector ist healthy wenn disabled oder API-Keys vorhanden."""
        if not self._enabled:
            return True
        return any([self._glassnode_key, self._cryptoquant_key, self._whale_alert_key])
