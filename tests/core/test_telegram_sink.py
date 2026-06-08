"""Tests for TelegramSink notification sink."""

from unittest.mock import MagicMock, patch

import requests

from core.notifications.telegram_sink import TelegramSink
from core.watchdog import WatchdogAlert, WatchdogSeverity


def _make_alert(**overrides):
    defaults = {
        "component": "test-component",
        "severity": WatchdogSeverity.WARNING,
        "message": "Something is wrong",
    }
    defaults.update(overrides)
    return WatchdogAlert(**defaults)


class TestTelegramSinkUnconfigured:
    """When bot_token or chat_id missing, sink silently skips."""

    def test_no_token_skips(self):
        sink = TelegramSink(bot_token=None, chat_id="123")
        alert = _make_alert()
        sink.send(alert)
        assert sink.stats["skipped"] == 1
        assert sink.stats["sent"] == 0

    def test_no_chat_id_skips(self):
        sink = TelegramSink(bot_token="tok", chat_id=None)
        alert = _make_alert()
        sink.send(alert)
        assert sink.stats["skipped"] == 1

    def test_both_missing_skips(self):
        sink = TelegramSink()
        alert = _make_alert()
        sink.send(alert)
        assert sink.stats["skipped"] == 1

    def test_no_http_call_when_unconfigured(self):
        sink = TelegramSink()
        with patch("requests.post") as mock_post:
            sink.send(_make_alert())
            mock_post.assert_not_called()


class TestTelegramSinkDryRun:
    """Dry-run mode logs but doesn't send."""

    def test_dry_run_counts_as_sent(self):
        sink = TelegramSink(bot_token="tok", chat_id="123", dry_run=True)
        sink.send(_make_alert())
        assert sink.stats["sent"] == 1
        assert sink.stats["errors"] == 0

    def test_dry_run_no_http_call(self):
        sink = TelegramSink(bot_token="tok", chat_id="123", dry_run=True)
        with patch("requests.post") as mock_post:
            sink.send(_make_alert())
            mock_post.assert_not_called()


class TestTelegramSinkSend:
    """Actual sending via mocked HTTP."""

    def test_successful_send(self):
        sink = TelegramSink(bot_token="tok123", chat_id="chat456", min_interval_seconds=0)
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()

        with patch("requests.post", return_value=mock_resp) as mock_post:
            sink.send(_make_alert())
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert "tok123" in call_args[0][0]
            assert call_args[1]["json"]["chat_id"] == "chat456"
            assert "HTML" == call_args[1]["json"]["parse_mode"]

        assert sink.stats["sent"] == 1

    def test_send_failure_handled(self):
        sink = TelegramSink(bot_token="tok", chat_id="123", min_interval_seconds=0)
        with patch("requests.post", side_effect=requests.ConnectionError("timeout")):
            sink.send(_make_alert())

        assert sink.stats["errors"] == 1
        assert sink.stats["sent"] == 0

    def test_http_error_handled(self):
        sink = TelegramSink(bot_token="tok", chat_id="123", min_interval_seconds=0)
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.raise_for_status.side_effect = requests.HTTPError(response=mock_resp)

        with patch("requests.post", return_value=mock_resp):
            sink.send(_make_alert())

        assert sink.stats["errors"] == 1


class TestTelegramSinkRateLimiting:
    """Rate limiting between sends."""

    def test_rate_limit_skips_second_send(self):
        sink = TelegramSink(bot_token="tok", chat_id="123", min_interval_seconds=600.0)
        with patch("requests.post") as mock_post:
            mock_post.return_value.raise_for_status = MagicMock()
            sink.send(_make_alert())
            sink.send(_make_alert())

        # First sent, second rate-limited
        assert sink.stats["sent"] == 1
        assert sink.stats["skipped"] == 1

    def test_zero_interval_sends_all(self):
        sink = TelegramSink(bot_token="tok", chat_id="123", min_interval_seconds=0)
        with patch("requests.post") as mock_post:
            mock_post.return_value.raise_for_status = MagicMock()
            sink.send(_make_alert())
            sink.send(_make_alert())

        assert sink.stats["sent"] == 2


class TestTelegramSinkMessageFormat:
    """Message formatting."""

    def test_warning_emoji(self):
        alert = _make_alert(severity=WatchdogSeverity.WARNING)
        msg = TelegramSink._format_message(alert)
        assert "⚠️" in msg
        assert "WARNING" in msg

    def test_critical_emoji(self):
        alert = _make_alert(severity=WatchdogSeverity.CRITICAL)
        msg = TelegramSink._format_message(alert)
        assert "🔴" in msg
        assert "CRITICAL" in msg

    def test_info_emoji(self):
        alert = _make_alert(severity=WatchdogSeverity.INFO)
        msg = TelegramSink._format_message(alert)
        assert "ℹ️" in msg

    def test_details_included(self):
        alert = _make_alert(details={"age_seconds": 300, "threshold": 120})
        msg = TelegramSink._format_message(alert)
        assert "age_seconds" in msg
        assert "300" in msg

    def test_no_details_section_when_empty(self):
        alert = _make_alert()
        msg = TelegramSink._format_message(alert)
        assert "Details" not in msg

    def test_timestamp_formatted(self):
        alert = _make_alert(timestamp=1700000000.0)
        msg = TelegramSink._format_message(alert)
        assert "UTC" in msg

    def test_html_formatting(self):
        alert = _make_alert()
        msg = TelegramSink._format_message(alert)
        assert "<b>" in msg
        assert "<code>" in msg


class TestTelegramSinkStats:
    """Stats tracking."""

    def test_stats_initial(self):
        sink = TelegramSink()
        assert sink.stats == {"sent": 0, "skipped": 0, "errors": 0}

    def test_stats_after_mixed_operations(self):
        sink = TelegramSink(bot_token="tok", chat_id="123", min_interval_seconds=600, dry_run=True)
        sink.send(_make_alert())  # sent (dry-run, updates last_send_time)
        sink.send(_make_alert())  # skipped (rate-limited)
        assert sink.stats["sent"] == 1
        assert sink.stats["skipped"] == 1


class TestTelegramSinkHtmlEscaping:
    """HTML escaping prevents injection in Telegram messages."""

    def test_component_angle_brackets_escaped(self):
        alert = _make_alert(component="<script>alert('xss')</script>")
        msg = TelegramSink._format_message(alert)
        assert "<script>" not in msg
        assert "&lt;script&gt;" in msg

    def test_message_ampersand_escaped(self):
        alert = _make_alert(message="Price dropped & recovered")
        msg = TelegramSink._format_message(alert)
        assert "&amp;" in msg

    def test_details_values_escaped(self):
        alert = _make_alert(details={"error": "JSON <failed> at line &5"})
        msg = TelegramSink._format_message(alert)
        assert "&lt;failed&gt;" in msg
        assert "&amp;" in msg

    def test_normal_text_unchanged(self):
        alert = _make_alert(component="legacy", message="Heartbeat stale")
        msg = TelegramSink._format_message(alert)
        assert "legacy" in msg
        assert "Heartbeat stale" in msg
