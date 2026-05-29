from __future__ import annotations

from execution.execution_models import OrderRequest
from execution.execution_guards import validate_order_request, sanitize_pair


def _make_request(**overrides) -> OrderRequest:
    defaults = dict(pair="BTC/USDT", action="BUY", price=50000.0, quantity=0.1, signal_confidence=80)
    defaults.update(overrides)
    return OrderRequest(**defaults)


# -- 1. test_valid_request --
def test_valid_request():
    request = _make_request()
    valid, reason = validate_order_request(request)
    assert valid is True
    assert reason == "valid"


# -- 2. test_invalid_price --
def test_invalid_price():
    request = _make_request(price=-1.0)
    valid, reason = validate_order_request(request)
    assert valid is False
    assert "price" in reason


# -- 3. test_invalid_quantity --
def test_invalid_quantity():
    request = _make_request(quantity=0.0)
    valid, reason = validate_order_request(request)
    assert valid is False
    assert "quantity" in reason


# -- 4. test_invalid_action --
def test_invalid_action():
    request = _make_request(action="HODL")
    valid, reason = validate_order_request(request)
    assert valid is False
    assert "action" in reason


# -- 5. test_sanitize_pair --
def test_sanitize_pair():
    assert sanitize_pair("btc/usdt") == "BTCUSDT"
    assert sanitize_pair("BTC/USDT") == "BTCUSDT"
    assert sanitize_pair("BTC USDT") == "BTCUSDT"
    assert sanitize_pair("eth / usdt") == "ETHUSDT"


# -- 6. test_valid_sell_request --
def test_valid_sell_request():
    request = _make_request(action="SELL")
    valid, reason = validate_order_request(request)
    assert valid is True


# -- 7. test_valid_hold_request --
def test_valid_hold_request():
    request = _make_request(action="HOLD")
    valid, reason = validate_order_request(request)
    assert valid is True


# -- 8. test_zero_price_invalid --
def test_zero_price_invalid():
    request = _make_request(price=0.0)
    valid, reason = validate_order_request(request)
    assert valid is False
