# integrations/freqtrade_strategy.py
"""
Freqtrade Custom Strategy that consumes signals from Rainbow Intelligence Engine.

## Installation

1. Copy this file to your Freqtrade user_data/strategies/ directory:
   cp integrations/freqtrade_strategy.py /path/to/freqtrade/user_data/strategies/rainbow_signal_strategy.py

2. Set environment variable or edit RAINBOW_API_URL below:
   export RAINBOW_API_URL=http://your-rainbow-engine-host:8000

3. Configure Freqtrade to use the strategy:
   freqtrade trade --strategy RainbowSignalStrategy

## Signal Flow

   Rainbow Engine → GET /signals/latest → FreqtradeSignalBridge → populate_entry_trend()

## Configuration

- RAINBOW_API_URL: Rainbow Engine base URL (default: http://localhost:8000)
- CONFIDENCE_THRESHOLD: Minimum confidence to enter a trade (default: 65)
- AI_CONFIDENCE_MIN: Minimum ai_confidence to enter (default: 0.3)

## Constraints

- This strategy only generates entry signals based on Rainbow Engine data.
- Exits are handled by Freqtrade's default ROI/stoploss mechanism.
- Only dry-run mode is recommended until thoroughly tested.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Allow importing the bridge from the ai4trade-bot project
# If installed as a package, this is not needed
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

try:
    from freqtrade.strategy import IStrategy, DecimalParameter, IntParameter
    from pandas import DataFrame
except ImportError:
    # Provide stubs for development/testing without freqtrade installed
    class IStrategy:  # type: ignore[no-redef]
        pass

    class DecimalParameter:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs): pass

    class IntParameter:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs): pass

    class DataFrame:  # type: ignore[no-redef]
        pass

from integrations.freqtrade_bridge import FreqtradeSignalBridge

logger = logging.getLogger(__name__)


class RainbowSignalStrategy(IStrategy):
    """
    Freqtrade strategy that consumes signals from the Rainbow Intelligence Engine.

    Signal Pipeline:
        Rainbow Engine → FreqtradeSignalBridge.get_signal() → populate_entry_trend()

    Only enters trades when confidence >= threshold (default: 65).
    """

    # Strategy metadata
    INTERFACE_VERSION = 3

    # Minimal ROI table — let signals drive exits
    minimal_roi = {
        "0": 0.10,    # 10% profit
        "60": 0.05,   # 5% after 1h
        "240": 0.02,  # 2% after 4h
    }

    # Stoploss
    stoploss = -0.05  # 5% stop loss

    # Timeframe
    timeframe = "1h"

    # Signal parameters
    confidence_threshold = int(os.getenv("CONFIDENCE_THRESHOLD", "65"))
    ai_confidence_min = float(os.getenv("AI_CONFIDENCE_MIN", "0.3"))

    # Trailing stop
    trailing_stop = True
    trailing_stop_positive = 0.01
    trailing_stop_positive_offset = 0.03
    trailing_only_offset_is_reached = True

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(config)
        self._bridge = FreqtradeSignalBridge()

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        No custom indicators needed — signals come from Rainbow Engine.
        Freqtrade's built-in indicators are sufficient for basic analysis.
        """
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Populate entry signals based on Rainbow Engine signals.

        For each pair, polls the Rainbow Engine for the latest signal
        and sets enter_long/enter_short accordingly.
        """
        pair = metadata.get("pair", "")

        try:
            signal = self._bridge.get_signal(pair)
        except Exception as exc:
            logger.warning("Signal fetch failed for %s: %s", pair, exc)
            return dataframe

        action = signal.get("action", "HOLD")
        confidence = signal.get("confidence", 0)
        ai_confidence = signal.get("ai_confidence", 0.0)

        # Only enter if confidence thresholds are met
        if confidence >= self.confidence_threshold and ai_confidence >= self.ai_confidence_min:
            if action == "BUY":
                dataframe["enter_long"] = 1
                logger.info(
                    "LONG signal for %s: confidence=%d ai_conf=%.2f",
                    pair, confidence, ai_confidence,
                )
            elif action == "SELL":
                # For short trading (if supported by exchange config)
                dataframe["enter_short"] = 1
                logger.info(
                    "SHORT signal for %s: confidence=%d ai_conf=%.2f",
                    pair, confidence, ai_confidence,
                )

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Exit logic is handled by ROI/stoploss/trailing stop.
        No custom exit logic from Rainbow Engine.
        """
        return dataframe
