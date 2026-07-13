"""Performance metrics for a simulated backtest only."""

from __future__ import annotations

from math import sqrt
from statistics import mean, stdev
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backtesting.engine import Trade


def sharpe_ratio(
    returns: list[float],
    risk_free: float = 0.0,
    periods_per_year: int = 365,
) -> float:
    """Return the annualized Sharpe ratio for periodic decimal returns."""
    if len(returns) < 2:
        return 0.0
    periodic_risk_free = risk_free / periods_per_year
    excess_returns = [value - periodic_risk_free for value in returns]
    volatility = stdev(excess_returns)
    if volatility == 0:
        return 0.0
    return mean(excess_returns) / volatility * sqrt(periods_per_year)


def sortino_ratio(returns: list[float], risk_free: float = 0.0) -> float:
    """Return the annualized Sortino ratio using downside volatility only."""
    if len(returns) < 2:
        return 0.0
    periodic_risk_free = risk_free / 365
    excess_returns = [value - periodic_risk_free for value in returns]
    downside = [min(0.0, value) for value in excess_returns]
    downside_deviation = sqrt(sum(value * value for value in downside) / len(downside))
    if downside_deviation == 0:
        return 0.0
    return mean(excess_returns) / downside_deviation * sqrt(365)


def max_drawdown(equity_curve: list[float]) -> float:
    """Return maximum drawdown as a negative decimal percentage."""
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    drawdown = 0.0
    for equity in equity_curve:
        peak = max(peak, equity)
        if peak > 0:
            drawdown = min(drawdown, (equity - peak) / peak)
    return drawdown


def win_rate(trades: list[Trade]) -> float:
    """Return the fraction of closed trades with positive PnL."""
    closed = [trade for trade in trades if trade.pnl_pct is not None]
    if not closed:
        return 0.0
    return sum(trade.pnl_pct > 0 for trade in closed) / len(closed)


def profit_factor(trades: list[Trade]) -> float:
    """Return gross profit divided by gross loss for closed trades."""
    pnl_values = [trade.pnl_pct for trade in trades if trade.pnl_pct is not None]
    gross_profit = sum(value for value in pnl_values if value > 0)
    gross_loss = abs(sum(value for value in pnl_values if value < 0))
    if gross_loss == 0:
        return float("inf") if gross_profit > 0 else 0.0
    return gross_profit / gross_loss


def calculate_all_metrics(equity_curve: list[float], trades: list[Trade]) -> dict[str, float | int]:
    """Aggregate return, risk and trade-quality metrics for a backtest."""
    returns = [
        equity_curve[index] / equity_curve[index - 1] - 1.0
        for index in range(1, len(equity_curve))
        if equity_curve[index - 1] != 0
    ]
    total_return_pct = 0.0
    if len(equity_curve) > 1 and equity_curve[0] != 0:
        total_return_pct = (equity_curve[-1] / equity_curve[0] - 1.0) * 100.0
    return {
        "sharpe_ratio": sharpe_ratio(returns),
        "sortino_ratio": sortino_ratio(returns),
        "max_drawdown": max_drawdown(equity_curve),
        "win_rate": win_rate(trades),
        "profit_factor": profit_factor(trades),
        "total_return_pct": total_return_pct,
        "total_trades": len(trades),
    }
