from __future__ import annotations

import logging
import time

from core.signal_model import Signal
from execution.execution_models import ExecutionStatus
from execution.execution_models import OrderResult
from execution.order_executor import OrderExecutor

log = logging.getLogger(__name__)


class ShadowExecutor:
    """
    Shadow Mode Executor: Simuliert Trades mit echten Marktdaten.
    Keine echten Orders. Trackt simuliertes PnL.
    """

    def __init__(self, order_executor: OrderExecutor, repository=None):
        self._executor = order_executor
        self._repository = repository
        self._open_trades: dict[str, dict] = {}
        self._closed_trades: list[dict] = []
        self._total_pnl = 0.0
        self._trade_count = 0
        self._win_count = 0

    def process_signal(self, signal: Signal, context: dict | None = None) -> OrderResult:
        """
        Signal im Shadow Mode verarbeiten.
        BUY: Eröffne simulierte Position
        SELL: Schließe simulierte Position (realisiere PnL)
        HOLD: Ignorieren
        """
        result = self._executor.execute(signal, context)

        if result.status not in (ExecutionStatus.SUBMITTED,):
            return result

        pair = signal.pair

        if signal.action == "BUY" and pair not in self._open_trades:
            self._open_trade(signal)
        elif signal.action == "SELL" and pair in self._open_trades:
            self._close_trade(signal)

        return result

    def get_performance(self) -> dict:
        """Shadow-Performance Metriken."""
        win_rate = (self._win_count / self._trade_count * 100) if self._trade_count > 0 else 0.0
        return {
            "total_pnl": round(self._total_pnl, 4),
            "trade_count": self._trade_count,
            "win_count": self._win_count,
            "win_rate_pct": round(win_rate, 2),
            "open_trades": len(self._open_trades),
        }

    def _open_trade(self, signal: Signal) -> None:
        trade = {
            "pair": signal.pair,
            "entry_price": signal.price,
            "quantity": signal.quantity,
            "opened_at": time.time(),
            "confidence": signal.confidence,
        }
        self._open_trades[signal.pair] = trade
        self._audit("shadow_trade_opened", trade)
        log.info("Shadow BUY: %s @ %.2f", signal.pair, signal.price)

    def _close_trade(self, signal: Signal) -> None:
        trade = self._open_trades.pop(signal.pair)
        entry_price = trade["entry_price"]
        quantity = trade["quantity"]
        pnl = (signal.price - entry_price) * quantity

        closed = {
            **trade,
            "exit_price": signal.price,
            "pnl": round(pnl, 4),
            "closed_at": time.time(),
        }
        self._closed_trades.append(closed)
        self._total_pnl += pnl
        self._trade_count += 1
        if pnl > 0:
            self._win_count += 1

        self._audit("shadow_trade_closed", closed)
        log.info("Shadow SELL: %s PnL=%.4f", signal.pair, pnl)

    def _audit(self, event_type: str, details: dict) -> None:
        if self._repository is not None:
            self._repository.log_audit(event_type, details)
