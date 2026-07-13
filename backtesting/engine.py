"""Canonical envelope replay engine; it never submits exchange orders."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from backtesting.metrics import calculate_all_metrics
from backtesting.signal_replayer import eligible_signals
from core.signals.envelope import CanonicalSignalEnvelope, SignalDirection


@dataclass
class Trade:
    signal_id: str
    asset: str
    direction: str
    entry_price: float
    exit_price: float | None
    confidence: float
    opened_at: datetime
    closed_at: datetime | None
    pnl_pct: float | None


@dataclass
class BacktestResult:
    equity_curve: list[float]
    trades: list[Trade]
    metrics: dict[str, float | int]


class BacktestEngine:
    """Replay historical signals against supplied OHLCV data only."""

    CONFIDENCE_GATE = 0.65
    SLIPPAGE_BPS = 5
    FEE_BPS = 10

    def __init__(self, capital: float = 100_000.0):
        if capital <= 0:
            raise ValueError("capital must be positive")
        self.capital = capital
        self.equity_curve = [capital]
        self.trades: list[Trade] = []

    def run(
        self,
        signals: list[CanonicalSignalEnvelope],
        price_data: dict[str, list[dict[str, Any]]],
    ) -> BacktestResult:
        """Replay eligible directional signals against local price candles."""
        self.equity_curve = [self.capital]
        self.trades = []
        for signal in eligible_signals(signals, self.CONFIDENCE_GATE):
            trade = self._process_signal(signal, price_data.get(signal.asset, []))
            if trade is None:
                continue
            self.trades.append(trade)
            self.equity_curve.append(self.equity_curve[-1] * (1.0 + trade.pnl_pct / 100.0))
        return BacktestResult(
            equity_curve=list(self.equity_curve),
            trades=list(self.trades),
            metrics=calculate_all_metrics(self.equity_curve, self.trades),
        )

    def _process_signal(
        self,
        signal: CanonicalSignalEnvelope,
        candles: list[dict[str, Any]],
    ) -> Trade | None:
        ordered = sorted(candles, key=lambda candle: _parse_timestamp(candle["timestamp"]))
        entry_candle = next(
            (candle for candle in ordered if _parse_timestamp(candle["timestamp"]) >= signal.created_at),
            None,
        )
        if entry_candle is None:
            return None

        exit_at = signal.valid_until or (
            signal.created_at + timedelta(seconds=signal.invalidation.max_age_seconds)
        )
        exit_candle = next(
            (candle for candle in ordered if _parse_timestamp(candle["timestamp"]) >= exit_at),
            None,
        )
        if exit_candle is None:
            return None

        is_long = signal.direction == SignalDirection.BULLISH
        slippage = self.SLIPPAGE_BPS / 10_000.0
        fee_pct = 2 * self.FEE_BPS / 10_000.0 * 100.0
        raw_entry = float(entry_candle["open"])
        raw_exit = float(exit_candle["close"])
        entry_price = raw_entry * (1.0 + slippage if is_long else 1.0 - slippage)
        exit_price = raw_exit * (1.0 - slippage if is_long else 1.0 + slippage)
        gross_return = (
            (exit_price - entry_price) / entry_price
            if is_long
            else (entry_price - exit_price) / entry_price
        )
        pnl_pct = gross_return * 100.0 - fee_pct
        return Trade(
            signal_id=signal.id,
            asset=signal.asset,
            direction="long" if is_long else "short",
            entry_price=entry_price,
            exit_price=exit_price,
            confidence=signal.confidence,
            opened_at=_parse_timestamp(entry_candle["timestamp"]),
            closed_at=_parse_timestamp(exit_candle["timestamp"]),
            pnl_pct=pnl_pct,
        )


def _parse_timestamp(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
