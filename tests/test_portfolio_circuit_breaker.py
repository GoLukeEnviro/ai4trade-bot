import time
from unittest.mock import MagicMock

import pytest

from core.signal_model import Signal
from trading.portfolio_circuit_breaker import PortfolioCircuitBreaker


def _make_signal(action: str = "BUY") -> Signal:
    return Signal(
        pair="BTC/USDT", action=action, confidence=80, price=65000.0, quantity=0.1
    )


def _make_breaker(**config_overrides) -> PortfolioCircuitBreaker:
    return PortfolioCircuitBreaker(repository=None, config=config_overrides or None)


# -- 1. Initial State -------------------------------------------------------

def test_initial_state_inactive():
    cb = _make_breaker()
    assert cb.is_active() is False


# -- 2. Consecutive Losses ---------------------------------------------------

def test_consecutive_losses_triggers():
    cb = _make_breaker(max_consecutive_losses=5, max_daily_loss_pct=1.0)
    for _ in range(4):
        cb.record_trade_result(-0.01)
        assert cb.is_active() is False

    cb.record_trade_result(-0.01)
    assert cb.is_active() is True


def test_winning_trade_resets_consecutive_counter():
    cb = _make_breaker(max_consecutive_losses=3, max_daily_loss_pct=1.0)
    cb.record_trade_result(-0.01)
    cb.record_trade_result(-0.01)
    assert cb._consecutive_losses == 2

    cb.record_trade_result(0.05)
    assert cb._consecutive_losses == 0

    cb.record_trade_result(-0.01)
    cb.record_trade_result(-0.01)
    assert cb.is_active() is False


# -- 3. Daily Loss -----------------------------------------------------------

def test_daily_loss_triggers():
    cb = _make_breaker(max_daily_loss_pct=0.05)
    cb.record_trade_result(-600.0)
    assert cb.is_active() is True


def test_daily_loss_below_threshold_no_trigger():
    cb = _make_breaker(max_daily_loss_pct=0.10)
    cb.record_trade_result(-0.05)
    assert cb.is_active() is False


# -- 4. API Latency ----------------------------------------------------------

def test_api_latency_triggers():
    cb = _make_breaker(max_api_latency_seconds=10.0)
    for _ in range(9):
        cb.record_api_latency(0.5)
    assert cb.is_active() is False

    cb.record_api_latency(12.0)
    assert cb.is_active() is True


def test_api_latency_below_threshold_no_trigger():
    cb = _make_breaker(max_api_latency_seconds=10.0)
    for _ in range(10):
        cb.record_api_latency(2.0)
    assert cb.is_active() is False


# -- 5. Rejected Rate --------------------------------------------------------

def test_rejected_rate_triggers():
    cb = _make_breaker(max_rejected_rate_pct=0.10)
    for _ in range(9):
        cb.record_request_result(rejected=False)
    assert cb.is_active() is False

    cb.record_request_result(rejected=False)
    # 0 rejected out of 10 = 0%, no trigger
    assert cb.is_active() is False

    # Add 2 rejected out of 12 = 16.7% > 10%
    cb.record_request_result(rejected=True)
    cb.record_request_result(rejected=True)
    assert cb.is_active() is True


def test_rejected_rate_below_threshold_no_trigger():
    cb = _make_breaker(max_rejected_rate_pct=0.50)
    for _ in range(8):
        cb.record_request_result(rejected=False)
    cb.record_request_result(rejected=True)
    cb.record_request_result(rejected=True)
    # 2/10 = 20% < 50%
    assert cb.is_active() is False


# -- 6. Signal Blocking ------------------------------------------------------

def test_active_blocks_non_hold_signal():
    cb = _make_breaker()
    cb.activate("test activation")
    assert cb.is_active() is True

    allowed, reason = cb.check_signal(_make_signal("BUY"))
    assert allowed is False
    assert "ACTIVE" in reason


def test_active_allows_hold_signal():
    cb = _make_breaker()
    cb.activate("test activation")

    allowed, reason = cb.check_signal(_make_signal("HOLD"))
    assert allowed is True
    assert "HOLD allowed" in reason


def test_inactive_allows_all_signals():
    cb = _make_breaker()
    for action in ("BUY", "SELL", "HOLD"):
        allowed, reason = cb.check_signal(_make_signal(action))
        assert allowed is True
        assert "inactive" in reason


# -- 7. Deactivation ---------------------------------------------------------

def test_manual_deactivate_resets():
    cb = _make_breaker()
    cb.activate("test")
    assert cb.is_active() is True

    cb.deactivate()
    assert cb.is_active() is False

    allowed, _ = cb.check_signal(_make_signal("BUY"))
    assert allowed is True


def test_deactivate_clears_counters():
    cb = _make_breaker(max_daily_loss_pct=1.0)
    cb.record_trade_result(-0.01)
    cb.record_trade_result(-0.01)
    cb.record_api_latency(5.0)
    cb.record_request_result(rejected=True)

    cb.activate("test")
    cb.deactivate()

    assert cb._consecutive_losses == 0
    assert cb._daily_pnl == 0.0
    assert len(cb._api_latencies) == 0
    assert cb._rejected_count == 0
    assert cb._total_requests == 0


# -- 8. Persistence via Repository -------------------------------------------

def test_state_persists_via_repository():
    repo = MagicMock()
    repo.get_state.side_effect = lambda key, default="": {
        "circuit_breaker_active": "1",
        "circuit_breaker_activated_at": "1700000000.0",
    }.get(key, default)

    cb = PortfolioCircuitBreaker(repository=repo)
    assert cb.is_active() is True
    assert cb._activated_at == 1700000000.0


def test_save_state_on_activate():
    repo = MagicMock()
    repo.get_state.return_value = "0"
    cb = PortfolioCircuitBreaker(repository=repo)

    cb.activate("automatic test")
    assert repo.set_state.call_count >= 2
    repo.set_state.assert_any_call("circuit_breaker_active", "1")


def test_save_state_on_deactivate():
    repo = MagicMock()
    repo.get_state.side_effect = lambda key, default="": {
        "circuit_breaker_active": "1",
        "circuit_breaker_activated_at": "1700000000.0",
    }.get(key, default)
    cb = PortfolioCircuitBreaker(repository=repo)

    cb.deactivate()
    repo.set_state.assert_any_call("circuit_breaker_active", "0")


def test_audit_called_on_activate():
    repo = MagicMock()
    repo.get_state.return_value = "0"
    cb = PortfolioCircuitBreaker(repository=repo)

    cb.activate("test reason")
    repo.log_audit.assert_called_once_with(
        "circuit_breaker_activated", {"reason": "test reason"}
    )


def test_audit_called_on_deactivate():
    repo = MagicMock()
    repo.get_state.side_effect = lambda key, default="": {
        "circuit_breaker_active": "1",
        "circuit_breaker_activated_at": "1700000000.0",
    }.get(key, default)
    cb = PortfolioCircuitBreaker(repository=repo)

    cb.deactivate()
    repo.log_audit.assert_called_once_with("circuit_breaker_deactivated", {})


# -- 9. Config Override ------------------------------------------------------

def test_config_override_works():
    cb = _make_breaker(max_consecutive_losses=2, max_daily_loss_pct=1.0)
    cb.record_trade_result(-0.01)
    assert cb.is_active() is False
    cb.record_trade_result(-0.01)
    assert cb.is_active() is True


def test_default_config_values():
    cb = _make_breaker()
    assert cb._config["max_consecutive_losses"] == 5
    assert cb._config["max_daily_loss_pct"] == 0.10
    assert cb._config["max_api_latency_seconds"] == 10.0
    assert cb._config["max_rejected_rate_pct"] == 0.10


# -- 10. Re-activation guard -------------------------------------------------

def test_activate_when_already_active_is_noop():
    cb = _make_breaker()
    cb.activate("first reason")
    first_activation_time = cb._activated_at

    time.sleep(0.01)
    cb.activate("second reason")
    assert cb._activated_at == first_activation_time
