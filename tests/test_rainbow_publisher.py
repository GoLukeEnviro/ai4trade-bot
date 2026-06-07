# tests/test_rainbow_publisher.py
"""Tests for adapters.rainbow_publisher.RainbowApiPublisher."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from adapters.rainbow_publisher import RainbowApiPublisher
from core.signal_model import Signal


def _make_signal(action: str = "BUY", confidence: int = 75) -> Signal:
    return Signal(pair="BTC/USDT", action=action, confidence=confidence, price=50000.0, quantity=0.1)


def test_publish_success() -> None:
    publisher = RainbowApiPublisher(base_url="http://localhost:8000")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status": "ok", "signal_id": "abc-123"}

    with patch("adapters.rainbow_publisher.requests.post", return_value=mock_resp) as mock_post:
        result = publisher.publish(_make_signal())

    assert result is True
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    assert call_kwargs[0][0] == "http://localhost:8000/signals/ingest"
    payload = call_kwargs[1]["json"]
    assert payload["asset"] == "BTCUSDT"
    assert payload["direction"] == "bullish"
    assert payload["strength"] == 0.75


def test_publish_server_error() -> None:
    publisher = RainbowApiPublisher(base_url="http://localhost:8000")
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error"

    with patch("adapters.rainbow_publisher.requests.post", return_value=mock_resp):
        result = publisher.publish(_make_signal())

    assert result is False


def test_publish_connection_error() -> None:
    publisher = RainbowApiPublisher(base_url="http://localhost:8000")
    import requests

    with patch("adapters.rainbow_publisher.requests.post", side_effect=requests.ConnectionError("refused")):
        result = publisher.publish(_make_signal())

    assert result is False


def test_map_action_buy() -> None:
    assert RainbowApiPublisher._map_action("BUY") == "bullish"


def test_map_action_sell() -> None:
    assert RainbowApiPublisher._map_action("SELL") == "bearish"


def test_map_action_hold() -> None:
    assert RainbowApiPublisher._map_action("HOLD") == "neutral"


def test_map_action_unknown() -> None:
    assert RainbowApiPublisher._map_action("UNKNOWN") == "neutral"


def test_publish_sell_signal() -> None:
    publisher = RainbowApiPublisher(base_url="http://localhost:8000")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status": "ok", "signal_id": "def-456"}

    with patch("adapters.rainbow_publisher.requests.post", return_value=mock_resp) as mock_post:
        result = publisher.publish(_make_signal(action="SELL", confidence=60))

    assert result is True
    payload = mock_post.call_args[1]["json"]
    assert payload["direction"] == "bearish"
    assert payload["strength"] == 0.6


def test_publish_confidence_clamped() -> None:
    publisher = RainbowApiPublisher(base_url="http://localhost:8000")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status": "ok"}

    with patch("adapters.rainbow_publisher.requests.post", return_value=mock_resp) as mock_post:
        publisher.publish(_make_signal(confidence=150))

    payload = mock_post.call_args[1]["json"]
    assert payload["strength"] == 1.0
    assert payload["confidence"] == 1.0
