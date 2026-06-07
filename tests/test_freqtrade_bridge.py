# tests/test_freqtrade_bridge.py
"""Tests for integrations.freqtrade_bridge.FreqtradeSignalBridge."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from integrations.freqtrade_bridge import FreqtradeSignalBridge


def _mock_response(status_code: int = 200, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or []
    return resp


def test_get_signal_buy() -> None:
    bridge = FreqtradeSignalBridge(api_url="http://localhost:8000", min_request_interval=0.0)
    data = [{
        "direction": "bullish",
        "confidence": 0.80,
        "ai_evaluation": {"ai_confidence": 0.75},
        "signal_id": "test-1",
        "asset": "BTCUSDT",
        "source": "ta_1h",
    }]
    with patch("integrations.freqtrade_bridge.requests.get", return_value=_mock_response(200, data)):
        result = bridge.get_signal("BTC/USDT")

    assert result["action"] == "BUY"
    assert result["confidence"] == 80
    assert result["ai_confidence"] == 0.75


def test_get_signal_sell() -> None:
    bridge = FreqtradeSignalBridge(api_url="http://localhost:8000", min_request_interval=0.0)
    data = [{"direction": "bearish", "confidence": 0.65}]
    with patch("integrations.freqtrade_bridge.requests.get", return_value=_mock_response(200, data)):
        result = bridge.get_signal("BTC/USDT")

    assert result["action"] == "SELL"
    assert result["confidence"] == 65


def test_get_signal_empty_response() -> None:
    bridge = FreqtradeSignalBridge(api_url="http://localhost:8000", min_request_interval=0.0)
    with patch("integrations.freqtrade_bridge.requests.get", return_value=_mock_response(200, [])):
        result = bridge.get_signal("BTC/USDT")

    assert result["action"] == "HOLD"
    assert result["confidence"] == 0


def test_get_signal_server_error() -> None:
    bridge = FreqtradeSignalBridge(api_url="http://localhost:8000", min_request_interval=0.0)
    with patch("integrations.freqtrade_bridge.requests.get", return_value=_mock_response(500)):
        result = bridge.get_signal("BTC/USDT")

    assert result["action"] == "HOLD"


def test_get_signal_connection_error() -> None:
    import requests

    bridge = FreqtradeSignalBridge(api_url="http://localhost:8000", min_request_interval=0.0)
    with patch("integrations.freqtrade_bridge.requests.get", side_effect=requests.ConnectionError()):
        result = bridge.get_signal("BTC/USDT")

    assert result["action"] == "HOLD"
    assert result["confidence"] == 0


def test_get_signal_timeout() -> None:
    import requests

    bridge = FreqtradeSignalBridge(api_url="http://localhost:8000", min_request_interval=0.0)
    with patch("integrations.freqtrade_bridge.requests.get", side_effect=requests.Timeout()):
        result = bridge.get_signal("BTC/USDT")

    assert result["action"] == "HOLD"


def test_get_signal_rate_limit_uses_cache() -> None:
    bridge = FreqtradeSignalBridge(api_url="http://localhost:8000", min_request_interval=10.0)
    data = [{"direction": "bullish", "confidence": 0.90}]

    # First call populates cache
    with patch("integrations.freqtrade_bridge.requests.get", return_value=_mock_response(200, data)):
        result1 = bridge.get_signal("BTC/USDT")
    assert result1["action"] == "BUY"

    # Second call within rate limit — should use cache
    with patch("integrations.freqtrade_bridge.requests.get") as mock_get:
        result2 = bridge.get_signal("BTC/USDT")
        mock_get.assert_not_called()

    assert result2["action"] == "BUY"


def test_get_signal_no_ai_evaluation() -> None:
    bridge = FreqtradeSignalBridge(api_url="http://localhost:8000", min_request_interval=0.0)
    data = [{"direction": "bullish", "confidence": 0.70}]
    with patch("integrations.freqtrade_bridge.requests.get", return_value=_mock_response(200, data)):
        result = bridge.get_signal("BTC/USDT")

    assert result["action"] == "BUY"
    assert result["ai_confidence"] == 0.0


def test_hold_fallback() -> None:
    result = FreqtradeSignalBridge._hold()
    assert result["action"] == "HOLD"
    assert result["confidence"] == 0
    assert result["ai_confidence"] == 0.0
