"""Smoke tests for the read-only canonical-signal backtesting package."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from backtesting.data_loader import load_fixture
from backtesting.engine import BacktestEngine, Trade
from backtesting.metrics import (
    calculate_all_metrics,
    max_drawdown,
    profit_factor,
    sharpe_ratio,
    sortino_ratio,
    win_rate,
)
from backtesting.report import generate_markdown_report
from backtesting.signal_replayer import eligible_signals
from core.signals.envelope import (
    Actionability,
    CanonicalSignalEnvelope,
    DataQuality,
    DataQualityStatus,
    SignalClass,
    SignalDirection,
)


def _signal(
    *,
    signal_id: str = "signal-1",
    direction: SignalDirection = SignalDirection.BULLISH,
    confidence: float = 0.80,
    quality: DataQualityStatus = DataQualityStatus.OK,
    created_at: datetime | None = None,
) -> CanonicalSignalEnvelope:
    return CanonicalSignalEnvelope(
        id=signal_id,
        signal_class=SignalClass.ENTRY,
        subtype="test_signal",
        source="backtest-test",
        asset="BTC/USDT:USDT",
        timeframe="1h",
        created_at=created_at or datetime(2026, 1, 1, tzinfo=UTC),
        direction=direction,
        confidence=confidence,
        risk_score=0.20,
        data_quality=DataQuality(status=quality),
        actionability=Actionability(can_alert=False),
        invalidation={"max_age_seconds": 3600},
    )


def _prices() -> dict[str, list[dict]]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return {
        "BTC/USDT:USDT": [
            {"timestamp": start.isoformat(), "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0},
            {
                "timestamp": (start + timedelta(hours=1)).isoformat(),
                "open": 110.0,
                "high": 112.0,
                "low": 109.0,
                "close": 110.0,
            },
        ]
    }


def test_engine_replays_eligible_signal_with_slippage_and_fees() -> None:
    result = BacktestEngine(capital=100_000).run([_signal()], _prices())

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.direction == "long"
    assert trade.entry_price == pytest.approx(100.05)
    assert trade.exit_price == pytest.approx(109.945)
    assert 0 < trade.pnl_pct < 10
    assert result.equity_curve[-1] > 100_000


def test_replayer_excludes_low_confidence_non_directional_and_bad_quality_signals() -> None:
    accepted = _signal(signal_id="accepted")
    rejected = [
        _signal(signal_id="low-confidence", confidence=0.64),
        _signal(signal_id="neutral", direction=SignalDirection.NEUTRAL),
        _signal(signal_id="stale", quality=DataQualityStatus.STALE),
    ]

    assert [signal.id for signal in eligible_signals(rejected + [accepted])] == ["accepted"]


def test_metrics_cover_returns_drawdown_and_trade_quality() -> None:
    trades = [
        Trade("win", "BTC/USDT:USDT", "long", 100, 110, 0.8, datetime.now(UTC), datetime.now(UTC), 10.0),
        Trade("loss", "BTC/USDT:USDT", "short", 100, 105, 0.8, datetime.now(UTC), datetime.now(UTC), -5.0),
    ]
    equity_curve = [100_000.0, 110_000.0, 88_000.0]

    assert sharpe_ratio([0.01, 0.02, -0.01]) > 0
    assert sortino_ratio([0.01, 0.02, -0.01]) > 0
    assert max_drawdown(equity_curve) == pytest.approx(-0.20)
    assert win_rate(trades) == pytest.approx(0.50)
    assert profit_factor(trades) == pytest.approx(2.0)
    assert calculate_all_metrics(equity_curve, trades)["total_trades"] == 2


def test_fixture_contains_30_days_of_ohlcv_and_20_canonical_signals(tmp_path: Path) -> None:
    fixture = load_fixture("backtesting/fixtures/btc_1h_sample.json")
    result = BacktestEngine().run(fixture.signals, fixture.price_data)
    report_path = tmp_path / "backtest.md"

    assert len(fixture.price_data["BTC/USDT:USDT"]) == 30 * 24
    assert len(fixture.signals) == 20
    assert result.metrics["sharpe_ratio"] >= -2.0
    assert "# Backtest Report" in generate_markdown_report(result, str(report_path))
    assert report_path.exists()
