import responses
from adapters.ai4trade_client import AI4TradeClient


@responses.activate
def test_get_me_wrapped_response():
    responses.get(
        "https://ai4trade.ai/api/claw/agents/me",
        json={"success": True, "data": {"id": 4234, "name": "Test"}},
    )
    c = AI4TradeClient(token="test-token")
    result = c.get_me()
    assert result["id"] == 4234
    assert result["name"] == "Test"


@responses.activate
def test_get_me_direct_json():
    responses.get(
        "https://ai4trade.ai/api/claw/agents/me",
        json={"id": 4234, "name": "Test", "email": "bot@test.ai"},
    )
    c = AI4TradeClient(token="test-token")
    result = c.get_me()
    assert result["id"] == 4234
    assert result["name"] == "Test"


@responses.activate
def test_publish_signal():
    responses.post(
        "https://ai4trade.ai/api/signals/realtime",
        json={"success": True},
    )
    c = AI4TradeClient(token="test-token")
    result = c.publish_signal(market="crypto", action="BUY", symbol="BTCUSDT", price=65000, quantity=0.1)
    assert result["success"] is True


@responses.activate
def test_token_expiry_raises_connection_error():
    responses.get("https://ai4trade.ai/api/claw/agents/me", status=401)
    c = AI4TradeClient(token="expired-token")
    try:
        c.get_me()
        assert False, "sollte Exception werfen"
    except ConnectionError as e:
        assert "401" in str(e)


@responses.activate
def test_get_positions():
    responses.get(
        "https://ai4trade.ai/api/positions",
        json={"success": True, "data": {"positions": []}},
    )
    c = AI4TradeClient(token="test-token")
    result = c.get_positions()
    assert result["positions"] == []


@responses.activate
def test_get_feed():
    responses.get(
        "https://ai4trade.ai/api/signals/feed",
        json={"success": True, "data": {"signals": [{"symbol": "BTCUSDT", "action": "BUY"}]}},
    )
    c = AI4TradeClient(token="test-token")
    result = c.get_feed()
    assert result["signals"][0]["symbol"] == "BTCUSDT"


@responses.activate
def test_auth_header_present():
    responses.get(
        "https://ai4trade.ai/api/claw/agents/me",
        json={"success": True, "data": {"id": 1}},
    )
    c = AI4TradeClient(token="test-token")
    c.get_me()
    req = responses.calls[0].request
    assert "Authorization" in req.headers
    assert req.headers["Authorization"].startswith("Bearer ")
