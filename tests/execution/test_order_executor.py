from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from core.signal_model import Signal
from execution.execution_models import ExecutionStatus
from execution.order_executor import OrderExecutor
from trading.policies.base import PolicyResult, Severity


def _make_signal(**overrides) -> Signal:
    defaults = dict(pair="BTC/USDT", action="BUY", confidence=80, price=50000.0, quantity=0.1)
    defaults.update(overrides)
    return Signal(**defaults)


# -- 1. test_execute_buy_success --
def test_execute_buy_success():
    publisher = MagicMock()
    publisher.publish.return_value = True
    executor = OrderExecutor(publisher=publisher)
    signal = _make_signal(action="BUY")
    result = executor.execute(signal)
    assert result.status == ExecutionStatus.SUBMITTED
    assert result.reason == "dry_run_mode"
    publisher.publish.assert_called_once_with(signal)


# -- 2. test_execute_sell_success --
def test_execute_sell_success():
    publisher = MagicMock()
    publisher.publish.return_value = True
    executor = OrderExecutor(publisher=publisher)
    signal = _make_signal(action="SELL")
    result = executor.execute(signal)
    assert result.status == ExecutionStatus.SUBMITTED
    assert result.reason == "dry_run_mode"
    publisher.publish.assert_called_once_with(signal)


# -- 3. test_execute_hold_skipped --
def test_execute_hold_skipped():
    publisher = MagicMock()
    executor = OrderExecutor(publisher=publisher)
    signal = _make_signal(action="HOLD")
    result = executor.execute(signal)
    assert result.status == ExecutionStatus.SKIPPED
    assert result.reason == "HOLD signal"
    publisher.publish.assert_not_called()


# -- 4. test_execute_circuit_breaker_blocks --
def test_execute_circuit_breaker_blocks():
    publisher = MagicMock()
    cb = MagicMock()
    cb.check_signal.return_value = (False, "circuit_breaker ACTIVE")
    executor = OrderExecutor(publisher=publisher, circuit_breaker=cb)
    signal = _make_signal()
    result = executor.execute(signal)
    assert result.status == ExecutionStatus.REJECTED
    assert "circuit_breaker" in result.reason
    publisher.publish.assert_not_called()


# -- 5. test_execute_safety_gateway_blocks --
def test_execute_safety_gateway_blocks():
    publisher = MagicMock()
    safety = MagicMock()
    safety.evaluate.return_value = PolicyResult(
        passed=False, severity=Severity.BLOCK, reason="risk too high", policy_name="TestPolicy"
    )
    executor = OrderExecutor(publisher=publisher, safety_gateway=safety)
    signal = _make_signal()
    result = executor.execute(signal)
    assert result.status == ExecutionStatus.REJECTED
    assert "risk too high" in result.reason
    publisher.publish.assert_not_called()


# -- 6. test_execute_publisher_fails --
def test_execute_publisher_fails():
    publisher = MagicMock()
    publisher.publish.return_value = False
    executor = OrderExecutor(publisher=publisher)
    signal = _make_signal()
    result = executor.execute(signal)
    assert result.status == ExecutionStatus.FAILED
    assert result.reason == "publish failed"


# -- 7. test_execute_publisher_exception --
def test_execute_publisher_exception():
    publisher = MagicMock()
    publisher.publish.side_effect = ConnectionError("network down")
    executor = OrderExecutor(publisher=publisher)
    signal = _make_signal()
    result = executor.execute(signal)
    assert result.status == ExecutionStatus.FAILED
    assert "network down" in result.reason


# -- 8. test_execute_no_publisher --
def test_execute_no_publisher():
    executor = OrderExecutor()
    signal = _make_signal()
    result = executor.execute(signal)
    assert result.status == ExecutionStatus.SKIPPED
    assert result.reason == "no publisher"


# -- 9. test_execute_no_safety_no_circuit --
def test_execute_no_safety_no_circuit():
    publisher = MagicMock()
    publisher.publish.return_value = True
    executor = OrderExecutor(publisher=publisher)
    signal = _make_signal()
    result = executor.execute(signal)
    assert result.status == ExecutionStatus.SUBMITTED
    publisher.publish.assert_called_once_with(signal)


# -- 10. test_signal_to_request_conversion --
def test_signal_to_request_conversion():
    executor = OrderExecutor()
    signal = _make_signal(pair="ETH/USDT", action="BUY", confidence=90, price=3000.0, quantity=1.5)
    request = executor._signal_to_request(signal)
    assert request.pair == "ETH/USDT"
    assert request.action == "BUY"
    assert request.price == 3000.0
    assert request.quantity == 1.5
    assert request.signal_confidence == 90
    assert request.mode == "dry_run"


# -- 11. test_execute_with_repository_audit --
def test_execute_with_repository_audit():
    publisher = MagicMock()
    publisher.publish.return_value = True
    repo = MagicMock()
    executor = OrderExecutor(publisher=publisher, repository=repo)
    signal = _make_signal()
    executor.execute(signal)
    repo.log_audit.assert_called_once()
    call_args = repo.log_audit.call_args
    assert call_args[0][0] == "execution_submitted"


# -- 12. test_execute_circuit_breaker_passes_then_safety_blocks --
def test_execute_circuit_breaker_passes_then_safety_blocks():
    publisher = MagicMock()
    cb = MagicMock()
    cb.check_signal.return_value = (True, "ok")
    safety = MagicMock()
    safety.evaluate.return_value = PolicyResult(
        passed=False, severity=Severity.BLOCK, reason="blocked by safety", policy_name="TestPolicy"
    )
    executor = OrderExecutor(publisher=publisher, safety_gateway=safety, circuit_breaker=cb)
    signal = _make_signal()
    result = executor.execute(signal)
    assert result.status == ExecutionStatus.REJECTED
    cb.check_signal.assert_called_once()
    safety.evaluate.assert_called_once()
