from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from core.signal_model import Signal
from execution.execution_models import ExecutionStatus
from execution.order_executor import OrderExecutor
from execution.shadow_executor import ShadowExecutor
from trading.policies.base import PolicyResult, Severity


def _make_signal(**overrides) -> Signal:
    defaults = dict(pair="BTC/USDT", action="BUY", confidence=80, price=50000.0, quantity=0.1)
    defaults.update(overrides)
    return Signal(**defaults)


def _make_executor(**overrides) -> OrderExecutor:
    defaults = {}
    defaults.update(overrides)
    return OrderExecutor(**defaults)


def _make_shadow(**executor_overrides) -> ShadowExecutor:
    executor = _make_executor(**executor_overrides)
    return ShadowExecutor(order_executor=executor)


# -- 1. test_buy_opens_shadow_trade --
def test_buy_opens_shadow_trade():
    publisher = MagicMock()
    publisher.publish.return_value = True
    shadow = _make_shadow(publisher=publisher)

    signal = _make_signal(action="BUY", price=50000.0, quantity=0.1)
    result = shadow.process_signal(signal)

    assert result.status == ExecutionStatus.SUBMITTED
    perf = shadow.get_performance()
    assert perf["open_trades"] == 1
    assert "BTC/USDT" in shadow._open_trades
    assert shadow._open_trades["BTC/USDT"]["entry_price"] == 50000.0
    assert shadow._open_trades["BTC/USDT"]["quantity"] == 0.1


# -- 2. test_sell_closes_shadow_trade_with_pnl --
def test_sell_closes_shadow_trade_with_pnl():
    publisher = MagicMock()
    publisher.publish.return_value = True
    shadow = _make_shadow(publisher=publisher)

    buy_signal = _make_signal(action="BUY", price=50000.0, quantity=0.1)
    shadow.process_signal(buy_signal)

    sell_signal = _make_signal(action="SELL", price=55000.0, quantity=0.1)
    result = shadow.process_signal(sell_signal)

    assert result.status == ExecutionStatus.SUBMITTED
    perf = shadow.get_performance()
    assert perf["open_trades"] == 0
    assert perf["trade_count"] == 1
    # pnl = (55000 - 50000) * 0.1 = 500.0
    assert perf["total_pnl"] == 500.0


# -- 3. test_sell_without_open_trade_ignored --
def test_sell_without_open_trade_ignored():
    publisher = MagicMock()
    publisher.publish.return_value = True
    shadow = _make_shadow(publisher=publisher)

    sell_signal = _make_signal(action="SELL", price=55000.0, quantity=0.1)
    result = shadow.process_signal(sell_signal)

    assert result.status == ExecutionStatus.SUBMITTED
    perf = shadow.get_performance()
    assert perf["open_trades"] == 0
    assert perf["trade_count"] == 0
    assert perf["total_pnl"] == 0.0


# -- 4. test_hold_ignored --
def test_hold_ignored():
    publisher = MagicMock()
    publisher.publish.return_value = True
    shadow = _make_shadow(publisher=publisher)

    hold_signal = _make_signal(action="HOLD")
    result = shadow.process_signal(hold_signal)

    assert result.status == ExecutionStatus.SKIPPED
    perf = shadow.get_performance()
    assert perf["open_trades"] == 0
    assert perf["trade_count"] == 0


# -- 5. test_safety_block_prevents_shadow_trade --
def test_safety_block_prevents_shadow_trade():
    publisher = MagicMock()
    safety = MagicMock()
    safety.evaluate.return_value = PolicyResult(
        passed=False, severity=Severity.BLOCK, reason="risk too high", policy_name="TestPolicy"
    )
    shadow = _make_shadow(publisher=publisher, safety_gateway=safety)

    signal = _make_signal(action="BUY")
    result = shadow.process_signal(signal)

    assert result.status == ExecutionStatus.REJECTED
    perf = shadow.get_performance()
    assert perf["open_trades"] == 0
    assert perf["trade_count"] == 0


# -- 6. test_performance_metrics --
def test_performance_metrics():
    publisher = MagicMock()
    publisher.publish.return_value = True
    shadow = _make_shadow(publisher=publisher)

    # Trade 1: profit
    shadow.process_signal(_make_signal(action="BUY", price=100.0, quantity=1.0))
    shadow.process_signal(_make_signal(action="SELL", price=110.0, quantity=1.0))

    # Trade 2: loss
    shadow.process_signal(_make_signal(action="BUY", price=200.0, quantity=2.0))
    shadow.process_signal(_make_signal(action="SELL", price=190.0, quantity=2.0))

    perf = shadow.get_performance()
    # Trade 1: (110-100)*1 = 10, Trade 2: (190-200)*2 = -20, total: -10
    assert perf["total_pnl"] == -10.0
    assert perf["trade_count"] == 2
    assert perf["win_count"] == 1
    assert perf["win_rate_pct"] == 50.0
    assert perf["open_trades"] == 0


# -- 7. test_multiple_pairs_tracked_separately --
def test_multiple_pairs_tracked_separately():
    publisher = MagicMock()
    publisher.publish.return_value = True
    shadow = _make_shadow(publisher=publisher)

    shadow.process_signal(Signal(pair="BTC/USDT", action="BUY", confidence=80, price=50000.0, quantity=0.1))
    shadow.process_signal(Signal(pair="ETH/USDT", action="BUY", confidence=70, price=3000.0, quantity=1.0))

    perf = shadow.get_performance()
    assert perf["open_trades"] == 2
    assert "BTC/USDT" in shadow._open_trades
    assert "ETH/USDT" in shadow._open_trades

    # Close BTC
    shadow.process_signal(Signal(pair="BTC/USDT", action="SELL", confidence=80, price=55000.0, quantity=0.1))

    perf = shadow.get_performance()
    assert perf["open_trades"] == 1
    assert perf["trade_count"] == 1
    assert "BTC/USDT" not in shadow._open_trades
    assert "ETH/USDT" in shadow._open_trades


# -- 8. test_win_count_increments_only_on_profit --
def test_win_count_increments_only_on_profit():
    publisher = MagicMock()
    publisher.publish.return_value = True
    shadow = _make_shadow(publisher=publisher)

    # Losing trade
    shadow.process_signal(_make_signal(action="BUY", price=100.0, quantity=1.0))
    shadow.process_signal(_make_signal(action="SELL", price=90.0, quantity=1.0))

    perf = shadow.get_performance()
    assert perf["win_count"] == 0
    assert perf["trade_count"] == 1
    assert perf["total_pnl"] == -10.0

    # Winning trade
    shadow.process_signal(_make_signal(action="BUY", price=100.0, quantity=1.0))
    shadow.process_signal(_make_signal(action="SELL", price=120.0, quantity=1.0))

    perf = shadow.get_performance()
    assert perf["win_count"] == 1
    assert perf["trade_count"] == 2
    # -10 + 20 = 10
    assert perf["total_pnl"] == 10.0


# -- 9. test_audit_called_on_open_and_close --
def test_audit_called_on_open_and_close():
    publisher = MagicMock()
    publisher.publish.return_value = True
    repo = MagicMock()
    executor = _make_executor(publisher=publisher, repository=repo)
    shadow = ShadowExecutor(order_executor=executor, repository=repo)

    shadow.process_signal(_make_signal(action="BUY", price=50000.0, quantity=0.1))
    audit_events = [call[0][0] for call in repo.log_audit.call_args_list]
    assert "shadow_trade_opened" in audit_events

    shadow.process_signal(_make_signal(action="SELL", price=55000.0, quantity=0.1))
    audit_events = [call[0][0] for call in repo.log_audit.call_args_list]
    assert "shadow_trade_closed" in audit_events


# -- 10. test_no_repository_no_audit_error --
def test_no_repository_no_audit_error():
    publisher = MagicMock()
    publisher.publish.return_value = True
    shadow = _make_shadow(publisher=publisher)

    # Should not raise
    shadow.process_signal(_make_signal(action="BUY", price=50000.0, quantity=0.1))
    shadow.process_signal(_make_signal(action="SELL", price=55000.0, quantity=0.1))

    perf = shadow.get_performance()
    assert perf["trade_count"] == 1


# -- 11. test_circuit_breaker_blocks_shadow_trade --
def test_circuit_breaker_blocks_shadow_trade():
    publisher = MagicMock()
    cb = MagicMock()
    cb.check_signal.return_value = (False, "circuit_breaker ACTIVE")
    shadow = _make_shadow(publisher=publisher, circuit_breaker=cb)

    signal = _make_signal(action="BUY")
    result = shadow.process_signal(signal)

    assert result.status == ExecutionStatus.REJECTED
    perf = shadow.get_performance()
    assert perf["open_trades"] == 0


# -- 12. test_duplicate_buy_ignored --
def test_duplicate_buy_ignored():
    publisher = MagicMock()
    publisher.publish.return_value = True
    shadow = _make_shadow(publisher=publisher)

    shadow.process_signal(_make_signal(action="BUY", price=50000.0, quantity=0.1))
    shadow.process_signal(_make_signal(action="BUY", price=48000.0, quantity=0.2))

    perf = shadow.get_performance()
    assert perf["open_trades"] == 1
    # Entry price should remain from first BUY
    assert shadow._open_trades["BTC/USDT"]["entry_price"] == 50000.0
    assert shadow._open_trades["BTC/USDT"]["quantity"] == 0.1
