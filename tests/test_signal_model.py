# tests/test_signal_model.py
from core.signal_model import Intent, Signal


def test_signal_creation():
    s = Signal(pair="BTC/USDT", action="BUY", confidence=75, price=65000.0, quantity=0.1)
    assert s.pair == "BTC/USDT"
    assert s.action == "BUY"
    assert s.confidence == 75
    assert s.price == 65000.0
    assert s.quantity == 0.1


def test_signal_to_dict():
    s = Signal(pair="ETH/USDT", action="SELL", confidence=80, price=3000.0, quantity=1.5)
    d = s.to_dict()
    assert d["pair"] == "ETH/USDT"
    assert d["action"] == "SELL"
    assert d["mode"] == "dry_run"


def test_signal_mode_always_dry_run():
    s = Signal(pair="BTC/USDT", action="BUY", confidence=75, price=65000.0, quantity=0.1, mode="live")
    assert s.mode == "dry_run"


def test_intent_mode_always_dry_run():
    i = Intent(intent="close_positions", pair="BTC/USDT", requires_approval=True)
    assert i.mode == "dry_run"


def test_intent_mode_live_forced_to_dry_run():
    i = Intent(intent="close_positions", pair="BTC/USDT", requires_approval=True, mode="live")
    assert i.mode == "dry_run"


def test_intent_to_dict():
    i = Intent(intent="status", pair=None, requires_approval=False)
    d = i.to_dict()
    assert d["mode"] == "dry_run"
    assert d["intent"] == "status"
