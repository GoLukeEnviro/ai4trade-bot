"""Markdown reporting for offline backtest results."""

from __future__ import annotations

from math import isinf
from pathlib import Path

from backtesting.engine import BacktestResult


def generate_markdown_report(result: BacktestResult, output_path: str) -> str:
    """Write a concise Markdown summary to the requested report path."""
    metrics = result.metrics
    profit_factor = metrics["profit_factor"]
    profit_factor_text = "∞" if isinstance(profit_factor, float) and isinf(profit_factor) else f"{profit_factor:.2f}"
    report = "\n".join(
        [
            "# Backtest Report",
            "",
            "## Summary",
            "",
            f"- Trades: {metrics['total_trades']}",
            f"- Total return: {metrics['total_return_pct']:.2f}%",
            f"- Win rate: {metrics['win_rate']:.2%}",
            f"- Profit factor: {profit_factor_text}",
            f"- Sharpe ratio: {metrics['sharpe_ratio']:.2f}",
            f"- Sortino ratio: {metrics['sortino_ratio']:.2f}",
            f"- Maximum drawdown: {metrics['max_drawdown']:.2%}",
            "",
            "This report is based on a historical simulation only; it never authorizes execution.",
        ]
    )
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(report + "\n", encoding="utf-8")
    return report
