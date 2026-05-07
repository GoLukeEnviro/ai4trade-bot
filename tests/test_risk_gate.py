import pytest
from core.signal_model import Signal
from trading.risk_gate import RiskGate


def test_pass_when_under_limits():
    rg = RiskGate(starting_capital=100000, max_position_pct=0.10, max_drawdown_pct=0.20, max_positions=3)
    positions = [{"pair": "BTC/USDT", "value": 5000}]
    signal = Signal(pair="ETH/USDT", action="BUY", confidence=75, price=3000.0, quantity=0.3)
    result, reason = rg.check(signal, positions, current_capital=95000)
    assert result is True
    assert "ok" in reason


def test_block_on_max_positions():
    rg = RiskGate(starting_capital=100000, max_position_pct=0.10, max_drawdown_pct=0.20, max_positions=2)
    positions = [{"pair": "BTC/USDT", "value": 5000}, {"pair": "ETH/USDT", "value": 3000}]
    signal = Signal(pair="SOL/USDT", action="BUY", confidence=80, price=150.0, quantity=5)
    result, reason = rg.check(signal, positions, current_capital=92000)
    assert result is False
    assert "max_positions" in reason


def test_block_on_drawdown():
    rg = RiskGate(starting_capital=100000, max_position_pct=0.10, max_drawdown_pct=0.20, max_positions=3)
    positions = [{"pair": "BTC/USDT", "value": 5000}]
    signal = Signal(pair="ETH/USDT", action="BUY", confidence=90, price=3000.0, quantity=0.3)
    result, reason = rg.check(signal, positions, current_capital=78000)
    assert result is False
    assert "drawdown" in reason


def test_block_on_position_size():
    rg = RiskGate(starting_capital=100000, max_position_pct=0.10, max_drawdown_pct=0.20, max_positions=3)
    positions = []
    signal = Signal(pair="BTC/USDT", action="BUY", confidence=80, price=65000.0, quantity=0.2)
    result, reason = rg.check(signal, positions, current_capital=100000)
    assert result is False
    assert "position_size" in reason


def test_hold_signals_pass_through():
    rg = RiskGate(starting_capital=100000, max_position_pct=0.10, max_drawdown_pct=0.20, max_positions=3)
    signal = Signal(pair="BTC/USDT", action="HOLD", confidence=50, price=65000.0, quantity=0)
    result, reason = rg.check(signal, [], current_capital=100000)
    assert result is True
    assert "hold" in reason


def test_max_positions_zero_blocks_everything():
    rg = RiskGate(starting_capital=100000, max_positions=0)
    signal = Signal(pair="BTC/USDT", action="BUY", confidence=80, price=65000.0, quantity=0.1)
    result, reason = rg.check(signal, [], current_capital=100000)
    assert result is False
    assert "max_positions" in reason


def test_hold_passes_with_restrictive_limits():
    rg = RiskGate(starting_capital=1000, max_position_pct=0.0, max_drawdown_pct=0.0, max_positions=0)
    signal = Signal(pair="BTC/USDT", action="HOLD", confidence=50, price=65000.0, quantity=0)
    result, reason = rg.check(signal, [], current_capital=500)
    assert result is True
    assert "hold" in reason


def test_max_position_pct_zero_blocks_trades():
    rg = RiskGate(starting_capital=100000, max_position_pct=0.0, max_drawdown_pct=0.20, max_positions=3)
    signal = Signal(pair="BTC/USDT", action="BUY", confidence=80, price=100.0, quantity=0.01)
    result, reason = rg.check(signal, [], current_capital=100000)
    assert result is False
    assert "position_size" in reason


def test_max_drawdown_pct_zero_blocks_on_any_loss():
    rg = RiskGate(starting_capital=100000, max_position_pct=0.10, max_drawdown_pct=0.0, max_positions=3)
    signal = Signal(pair="BTC/USDT", action="BUY", confidence=80, price=100.0, quantity=0.01)
    result, reason = rg.check(signal, [], current_capital=99000)
    assert result is False
    assert "drawdown" in reason


def test_drawdown_zero_allows_no_loss():
    rg = RiskGate(starting_capital=100000, max_position_pct=0.10, max_drawdown_pct=0.0, max_positions=3)
    signal = Signal(pair="BTC/USDT", action="BUY", confidence=80, price=100.0, quantity=0.01)
    result, reason = rg.check(signal, [], current_capital=100000)
    assert result is True
    assert "ok" in reason


def test_starting_capital_zero_raises():
    with pytest.raises(ValueError, match="starting_capital"):
        RiskGate(starting_capital=0)


def test_starting_capital_negative_raises():
    with pytest.raises(ValueError, match="starting_capital"):
        RiskGate(starting_capital=-1000)


def test_sell_signal_checked_same_as_buy():
    rg = RiskGate(starting_capital=100000, max_position_pct=0.10, max_drawdown_pct=0.20, max_positions=3)
    positions = [{"pair": "BTC/USDT", "value": 5000}]
    signal = Signal(pair="BTC/USDT", action="SELL", confidence=75, price=65000.0, quantity=0.05)
    result, reason = rg.check(signal, positions, current_capital=95000)
    assert result is True
    assert "ok" in reason
