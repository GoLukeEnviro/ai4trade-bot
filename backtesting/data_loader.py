"""Fixture loading for deterministic, offline backtests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.signals.envelope import CanonicalSignalEnvelope


@dataclass(frozen=True)
class BacktestFixture:
    price_data: dict[str, list[dict[str, Any]]]
    signals: list[CanonicalSignalEnvelope]


def load_fixture(path: str | Path) -> BacktestFixture:
    """Load synthetic OHLCV and canonical envelopes from a local JSON fixture."""
    fixture_path = Path(path)
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    price_data = payload.get("price_data", {})
    signals = [CanonicalSignalEnvelope.model_validate(item) for item in payload.get("signals", [])]
    if not isinstance(price_data, dict):
        raise ValueError("fixture price_data must be an asset-to-candles mapping")
    return BacktestFixture(price_data=price_data, signals=signals)
