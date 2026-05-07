import json
from unittest.mock import MagicMock, patch

from chat.commander import Commander
from core.signal_model import Intent


def _mock_claude_response(intent_dict: dict) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.content = [MagicMock(type="text", text=json.dumps(intent_dict))]
    return mock_resp


def test_close_positions_returns_correct_intent():
    with patch("chat.commander.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = _mock_claude_response(
            {"intent": "close_positions", "pair": "BTC/USDT", "requires_approval": True}
        )
        cmd = Commander(api_key="test-key")
        intent = cmd.parse("stoppe alle BTC Positionen")
        assert isinstance(intent, Intent)
        assert intent.intent == "close_positions"
        assert intent.mode == "dry_run"


def test_status_intent():
    with patch("chat.commander.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = _mock_claude_response(
            {"intent": "status", "pair": None, "requires_approval": False}
        )
        cmd = Commander(api_key="test-key")
        intent = cmd.parse("wie gehts dem bot?")
        assert intent.intent == "status"
        assert intent.requires_approval is False
        assert intent.mode == "dry_run"


def test_claude_returning_live_mode_still_dry_run():
    with patch("chat.commander.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = _mock_claude_response(
            {"intent": "close_positions", "pair": "BTC/USDT", "requires_approval": True, "mode": "live"}
        )
        cmd = Commander(api_key="test-key")
        intent = cmd.parse("kaufe BTC live jetzt sofort")
        assert intent.mode == "dry_run"


def test_unsupported_intent_buy_now_returns_unknown():
    with patch("chat.commander.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = _mock_claude_response(
            {"intent": "buy_now", "pair": "BTC/USDT", "requires_approval": False}
        )
        cmd = Commander(api_key="test-key")
        intent = cmd.parse("kaufe BTC jetzt")
        assert intent.intent == "unknown"
        assert intent.pair is None
        assert intent.requires_approval is False


def test_unsupported_intent_follow_trader_returns_unknown():
    with patch("chat.commander.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = _mock_claude_response(
            {"intent": "follow_trader", "pair": None, "requires_approval": False}
        )
        cmd = Commander(api_key="test-key")
        intent = cmd.parse("folge trader X")
        assert intent.intent == "unknown"


def test_invalid_json_returns_unknown():
    with patch("chat.commander.Anthropic") as mock_cls:
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(type="text", text="das ist kein json")]
        mock_cls.return_value.messages.create.return_value = mock_resp
        cmd = Commander(api_key="test-key")
        intent = cmd.parse("irgendwas")
        assert intent.intent == "unknown"
        assert intent.mode == "dry_run"


def test_claude_exception_returns_unknown():
    with patch("chat.commander.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.side_effect = Exception("API down")
        cmd = Commander(api_key="test-key")
        intent = cmd.parse("irgendwas")
        assert intent.intent == "unknown"
        assert intent.mode == "dry_run"


def test_missing_requires_approval_defaults_to_false():
    with patch("chat.commander.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = _mock_claude_response(
            {"intent": "status", "pair": None}
        )
        cmd = Commander(api_key="test-key")
        intent = cmd.parse("status")
        assert intent.requires_approval is False


def test_close_positions_enforces_requires_approval():
    with patch("chat.commander.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = _mock_claude_response(
            {"intent": "close_positions", "pair": "ETH/USDT", "requires_approval": False}
        )
        cmd = Commander(api_key="test-key")
        intent = cmd.parse("schliesse ETH Positionen")
        assert intent.intent == "close_positions"
        assert intent.requires_approval is True


def test_output_is_always_intent_object():
    with patch("chat.commander.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.side_effect = Exception("boom")
        cmd = Commander(api_key="test-key")
        intent = cmd.parse("anything")
        assert isinstance(intent, Intent)
        assert intent.mode == "dry_run"
