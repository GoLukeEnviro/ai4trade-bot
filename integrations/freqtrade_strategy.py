"""Minimal Freqtrade IStrategy-compatible skeleton for advisory signal consumption.

This module provides a strategy class that bridges ai4trade-bot's canonical
signal intelligence into Freqtrade's populate_entry_trend / populate_exit_trend
interface. It is advisory-only and NEVER executes live trades.

Freqtrade is an optional dependency. If it is not installed, the strategy
class is still importable for testing purposes — it will simply have no
base class and will default all signals to HOLD.

Safety invariants:
  - No live trading — dry-run only
  - No order execution functions
  - No exchange credentials or API calls
  - HOLD is always the safe fallback
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional Freqtrade import
# ---------------------------------------------------------------------------

try:
    from freqtrade.strategy import IStrategy  # type: ignore[import-untyped]

    _FREQTRADE_AVAILABLE = True
except ImportError:
    _FREQTRADE_AVAILABLE = False

    class IStrategy:  # type: ignore[no-redef]  # noqa: F811
        """Stub base class when freqtrade is not installed."""

        def __init__(self, config: dict[str, Any] | None = None) -> None:
            self.config = config or {}

        # Freqtrade interface methods — no-ops in stub
        def populate_entry_trend(self, dataframe: Any, metadata: dict | None = None) -> Any:
            return dataframe

        def populate_exit_trend(self, dataframe: Any, metadata: dict | None = None) -> Any:
            return dataframe


# ---------------------------------------------------------------------------
# Strategy implementation
# ---------------------------------------------------------------------------

class AI4TradeSignalStrategy(IStrategy):
    """Advisory-only strategy that consumes ai4trade-bot signal bridge output.

    Configuration via strategy params (passed through Freqtrade config or
    constructor):

    - ``confidence_threshold`` (float, 0-1): minimum confidence for entries.
    - ``risk_threshold`` (float, 0-1): maximum risk_score for entries.
    - ``min_interval_seconds`` (float): rate-limit interval per pair.
    - ``cache_ttl_seconds`` (float): advisory cache TTL per pair.

    Freqtrade interface attributes:

    - ``stoploss``: -0.05 (5%)
    - ``minimal_roi``: conservative table
    - ``timeframe``: '5m'
    """

    # Conservative defaults
    stoploss: float = -0.05
    minimal_roi: dict[str, float] = {
        "0": 0.10,
        "30": 0.05,
        "60": 0.02,
    }
    timeframe: str = "5m"

    # Dry-run only — no live trading
    can_short: bool = False

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config=config) if _FREQTRADE_AVAILABLE else None
        self._bridge: Any = None

    @property
    def bridge(self) -> Any:
        """Lazy-initialize the FreqtradeBridge if possible."""
        if self._bridge is None:
            try:
                from core.signals.registry import CanonicalSignalRegistry
                from integrations.freqtrade_bridge import FreqtradeBridge

                registry_path = getattr(self, "config", {}).get(
                    "signal_registry_path", "storage/canonical_signals.db"
                )
                registry = CanonicalSignalRegistry(registry_path)
                bridge_params = {
                    "confidence_threshold": getattr(self, "confidence_threshold", 0.6),
                    "risk_threshold": getattr(self, "risk_threshold", 0.7),
                    "cache_ttl_seconds": getattr(self, "cache_ttl_seconds", 60.0),
                    "min_interval_seconds": getattr(self, "min_interval_seconds", 30.0),
                }
                self._bridge = FreqtradeBridge(registry, **bridge_params)
            except Exception as exc:
                log.warning("Failed to initialize FreqtradeBridge: %s", exc)
                self._bridge = None
        return self._bridge

    def populate_entry_trend(
        self, dataframe: Any, metadata: dict | None = None
    ) -> Any:
        """Populate entry signals based on advisory bridge output.

        Only marks entries when the bridge returns "long" with confidence above
        threshold and acceptable risk. Default: no entries (safe).
        """
        metadata = metadata or {}

        # If dataframe is a pandas DataFrame, add columns
        try:
            if hasattr(dataframe, "assign"):
                pair = metadata.get("pair", "")
                advisory = self._get_advisory(pair)
                if advisory and advisory.get("action") == "long":
                    dataframe["enter_long"] = 1
                else:
                    dataframe["enter_long"] = 0
        except Exception as exc:
            log.warning("populate_entry_trend error: %s", exc)
            try:
                if hasattr(dataframe, "assign"):
                    dataframe["enter_long"] = 0
            except Exception as inner_exc:
                log.warning("populate_entry_trend: fallback reset failed: %s", inner_exc)

        return dataframe

    def populate_exit_trend(
        self, dataframe: Any, metadata: dict | None = None
    ) -> Any:
        """Populate exit signals based on advisory bridge output.

        Only marks exits when the bridge returns "short". Default: no exits (safe).
        """
        metadata = metadata or {}

        try:
            if hasattr(dataframe, "assign"):
                pair = metadata.get("pair", "")
                advisory = self._get_advisory(pair)
                if advisory and advisory.get("action") == "short":
                    dataframe["exit_long"] = 1
                else:
                    dataframe["exit_long"] = 0
        except Exception as exc:
            log.warning("populate_exit_trend error: %s", exc)
            try:
                if hasattr(dataframe, "assign"):
                    dataframe["exit_long"] = 0
            except Exception as inner_exc:
                log.warning("populate_exit_trend: fallback reset failed: %s", inner_exc)

        return dataframe

    def _get_advisory(self, pair: str) -> dict[str, Any] | None:
        """Get latest advisory from bridge, with safe fallback."""
        try:
            if self.bridge is not None:
                return self.bridge.get_latest_signal(pair)
        except Exception as exc:
            log.warning("Advisory lookup failed for pair=%s: %s", pair, exc)
        return None
