from unittest.mock import MagicMock
from trading.position_state import PositionState


def test_refresh_loads_from_api():
    mock_client = MagicMock()
    mock_client.get_positions.return_value = {
        "positions": [
            {"pair": "BTC/USDT", "value": 5000, "action": "BUY"},
            {"pair": "ETH/USDT", "value": 3000, "action": "BUY"},
        ]
    }
    ps = PositionState(client=mock_client)
    ps.refresh()
    assert len(ps.positions) == 2
    assert ps.positions[0]["pair"] == "BTC/USDT"


def test_empty_positions():
    mock_client = MagicMock()
    mock_client.get_positions.return_value = {"positions": []}
    ps = PositionState(client=mock_client)
    ps.refresh()
    assert ps.positions == []


def test_missing_positions_key_defaults_to_empty():
    mock_client = MagicMock()
    mock_client.get_positions.return_value = {"data": []}
    ps = PositionState(client=mock_client)
    ps.refresh()
    assert ps.positions == []


def test_api_exception_does_not_crash():
    mock_client = MagicMock()
    mock_client.get_positions.side_effect = ConnectionError("API down")
    ps = PositionState(client=mock_client)
    ps.refresh()
    assert ps.positions == []


def test_api_exception_preserves_previous_positions():
    mock_client = MagicMock()
    mock_client.get_positions.return_value = {
        "positions": [{"pair": "BTC/USDT", "value": 5000}]
    }
    ps = PositionState(client=mock_client)
    ps.refresh()
    assert ps.count() == 1

    mock_client.get_positions.side_effect = ConnectionError("API down")
    ps.refresh()
    assert ps.count() == 1
    assert ps.positions[0]["pair"] == "BTC/USDT"


def test_count_returns_current_count():
    mock_client = MagicMock()
    mock_client.get_positions.return_value = {
        "positions": [{"pair": "BTC/USDT"}, {"pair": "ETH/USDT"}, {"pair": "SOL/USDT"}]
    }
    ps = PositionState(client=mock_client)
    ps.refresh()
    assert ps.count() == 3


def test_no_trading_methods_called():
    mock_client = MagicMock()
    mock_client.get_positions.return_value = {"positions": []}
    ps = PositionState(client=mock_client)
    ps.refresh()
    mock_client.publish_signal.assert_not_called()
    assert not hasattr(ps, "publish_signal")
