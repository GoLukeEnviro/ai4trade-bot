import json
from unittest.mock import MagicMock, patch

from chat.commander import Commander
from core.signal_model import Intent


def test_close_positions_returns_correct_intent():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = json.dumps(
        {"intent": "close_positions", "pair": "BTC/USDT", "requires_approval": True}
    )
    with patch("chat.commander.create_provider", return_value=mock_llm):
        cmd = Commander(api_key="test-key")
        intent = cmd.parse("stoppe alle BTC Positionen")
        assert isinstance(intent, Intent)
        assert intent.intent == "close_positions"
        assert intent.mode == "dry_run"


def test_status_intent():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = json.dumps(
        {"intent": "status", "pair": None, "requires_approval": False}
    )
    with patch("chat.commander.create_provider", return_value=mock_llm):
        cmd = Commander(api_key="test-key")
        intent = cmd.parse("wie gehts dem bot?")
        assert intent.intent == "status"
        assert intent.requires_approval is False
        assert intent.mode == "dry_run"


def test_llm_returning_live_mode_still_dry_run():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = json.dumps(
        {"intent": "close_positions", "pair": "BTC/USDT", "requires_approval": True, "mode": "live"}
    )
    with patch("chat.commander.create_provider", return_value=mock_llm):
        cmd = Commander(api_key="test-key")
        intent = cmd.parse("kaufe BTC live jetzt sofort")
        assert intent.mode == "dry_run"


def test_unsupported_intent_buy_now_returns_unknown():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = json.dumps(
        {"intent": "buy_now", "pair": "BTC/USDT", "requires_approval": False}
    )
    with patch("chat.commander.create_provider", return_value=mock_llm):
        cmd = Commander(api_key="test-key")
        intent = cmd.parse("kaufe BTC jetzt")
        assert intent.intent == "unknown"
        assert intent.pair is None
        assert intent.requires_approval is False


def test_unsupported_intent_follow_trader_returns_unknown():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = json.dumps(
        {"intent": "follow_trader", "pair": None, "requires_approval": False}
    )
    with patch("chat.commander.create_provider", return_value=mock_llm):
        cmd = Commander(api_key="test-key")
        intent = cmd.parse("folge trader X")
        assert intent.intent == "unknown"


def test_invalid_json_returns_unknown():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "das ist kein json"
    with patch("chat.commander.create_provider", return_value=mock_llm):
        cmd = Commander(api_key="test-key")
        intent = cmd.parse("irgendwas")
        assert intent.intent == "unknown"
        assert intent.mode == "dry_run"


def test_llm_exception_returns_unknown():
    mock_llm = MagicMock()
    mock_llm.complete.side_effect = Exception("API down")
    with patch("chat.commander.create_provider", return_value=mock_llm):
        cmd = Commander(api_key="test-key")
        intent = cmd.parse("irgendwas")
        assert intent.intent == "unknown"
        assert intent.mode == "dry_run"


def test_missing_requires_approval_defaults_to_false():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = json.dumps(
        {"intent": "status", "pair": None}
    )
    with patch("chat.commander.create_provider", return_value=mock_llm):
        cmd = Commander(api_key="test-key")
        intent = cmd.parse("status")
        assert intent.requires_approval is False


def test_close_positions_enforces_requires_approval():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = json.dumps(
        {"intent": "close_positions", "pair": "ETH/USDT", "requires_approval": False}
    )
    with patch("chat.commander.create_provider", return_value=mock_llm):
        cmd = Commander(api_key="test-key")
        intent = cmd.parse("schliesse ETH Positionen")
        assert intent.intent == "close_positions"
        assert intent.requires_approval is True


def test_output_is_always_intent_object():
    mock_llm = MagicMock()
    mock_llm.complete.side_effect = Exception("boom")
    with patch("chat.commander.create_provider", return_value=mock_llm):
        cmd = Commander(api_key="test-key")
        intent = cmd.parse("anything")
        assert isinstance(intent, Intent)
        assert intent.mode == "dry_run"
