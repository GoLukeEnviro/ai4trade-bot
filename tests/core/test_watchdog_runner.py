"""Tests for watchdog_runner module."""

import json
from unittest.mock import MagicMock, patch

import pytest

from core.watchdog_runner import (
    _build_components,
    _build_sinks,
    _default_config,
    load_config,
    run_watchdog,
)


class TestLoadConfig:
    """Config loading."""

    def test_loads_valid_config(self, tmp_path):
        cfg = {
            "components": [{"name": "x", "heartbeat_path": "/tmp/hb.json"}],
            "telegram": {"bot_token": "t", "chat_id": "c"},
        }
        p = tmp_path / "watchdog.json"
        p.write_text(json.dumps(cfg))

        result = load_config(str(p))
        assert result["components"][0]["name"] == "x"
        assert result["telegram"]["bot_token"] == "t"

    def test_missing_file_returns_default(self, tmp_path):
        result = load_config(str(tmp_path / "nonexistent.json"))
        assert "components" in result
        assert len(result["components"]) == 2  # legacy + rainbow

    def test_malformed_json_returns_default(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("not json{{{")
        result = load_config(str(p))
        assert "components" in result

    def test_default_config_has_two_components(self):
        cfg = _default_config()
        names = [c["name"] for c in cfg["components"]]
        assert "legacy" in names
        assert "rainbow" in names


class TestBuildComponents:
    """Component building from config."""

    def test_builds_from_config(self):
        cfg = {
            "components": [
                {"name": "a", "heartbeat_path": "/a.json", "stale_threshold_seconds": 60},
                {"name": "b", "heartbeat_path": "/b.json", "cooldown_seconds": 600},
            ]
        }
        comps = _build_components(cfg)
        assert len(comps) == 2
        assert comps[0].name == "a"
        assert comps[0].stale_threshold_seconds == 60
        assert comps[1].cooldown_seconds == 600

    def test_defaults_applied(self):
        cfg = {"components": [{"name": "x", "heartbeat_path": "/x.json"}]}
        comps = _build_components(cfg)
        assert comps[0].stale_threshold_seconds == 120.0
        assert comps[0].cooldown_seconds == 300.0

    def test_empty_components(self):
        comps = _build_components({"components": []})
        assert len(comps) == 0


class TestBuildSinks:
    """Sink building from config."""

    def test_always_has_log_sink(self):
        sinks = _build_sinks({})
        assert len(sinks) >= 1
        assert type(sinks[0]).__name__ == "LogNotificationSink"

    def test_telegram_sink_added_when_configured(self):
        sinks = _build_sinks({"telegram": {"bot_token": "t", "chat_id": "c"}})
        assert len(sinks) == 2
        assert type(sinks[1]).__name__ == "TelegramSink"

    def test_no_telegram_sink_for_missing_key(self):
        sinks = _build_sinks({})
        assert len(sinks) == 1

    def test_empty_telegram_config_creates_unconfigured_sink(self):
        sinks = _build_sinks({"telegram": {}})
        assert len(sinks) == 2
        assert sinks[1]._is_configured() is False

    def test_telegram_dry_run_from_config(self):
        sinks = _build_sinks({"telegram": {"bot_token": "t", "chat_id": "c", "dry_run": True}})
        assert sinks[1]._dry_run is True


class TestBuildSinksEnvFallback:
    """Environment variable fallback for Telegram credentials."""

    def test_env_fallback_bot_token(self):
        with patch.dict("os.environ", {"WATCHDOG_TELEGRAM_BOT_TOKEN": "env-token"}, clear=False):
            sinks = _build_sinks({"telegram": {"chat_id": "c"}})
            assert sinks[1]._bot_token == "env-token"

    def test_env_fallback_chat_id(self):
        with patch.dict("os.environ", {"WATCHDOG_TELEGRAM_CHAT_ID": "env-chat"}, clear=False):
            sinks = _build_sinks({"telegram": {"bot_token": "t"}})
            assert sinks[1]._chat_id == "env-chat"

    def test_config_takes_priority_over_env(self):
        with patch.dict("os.environ", {"WATCHDOG_TELEGRAM_BOT_TOKEN": "env-token"}, clear=False):
            sinks = _build_sinks({"telegram": {"bot_token": "config-token", "chat_id": "c"}})
            assert sinks[1]._bot_token == "config-token"

    def test_env_values_make_sink_configured(self):
        with patch.dict("os.environ", {
            "WATCHDOG_TELEGRAM_BOT_TOKEN": "env-tok",
            "WATCHDOG_TELEGRAM_CHAT_ID": "env-chat",
        }, clear=False):
            sinks = _build_sinks({"telegram": {}})
            assert sinks[1]._is_configured() is True


class TestRunWatchdog:
    """Watchdog runner loop."""

    def test_single_check_mode(self):
        """--once mode runs exactly one check."""
        cfg = _default_config()
        # Point to non-existent paths so we get alerts
        cfg["components"][0]["heartbeat_path"] = "/tmp/nonexistent_heartbeat_test.json"
        cfg["components"][1]["heartbeat_path"] = "/tmp/nonexistent_heartbeat_test2.json"

        with patch("core.watchdog_runner._build_sinks", return_value=[MagicMock()]), \
             patch("core.watchdog_runner._build_components", wraps=_build_components) as mock_build:
            run_watchdog(cfg, once=True)
            mock_build.assert_called_once()

    def test_shutdown_on_signal(self):
        """Watchdog stops on SIGTERM."""
        cfg = _default_config()
        # Simulate immediate shutdown
        with patch("core.watchdog_runner._build_sinks", return_value=[MagicMock()]), \
             patch("time.sleep", side_effect=KeyboardInterrupt):
            try:
                run_watchdog(cfg, interval=1)
            except KeyboardInterrupt:
                pass  # Expected, runner should handle SIGINT internally

    def test_no_components_exits(self):
        """Exit code 1 when no components configured."""
        cfg = {"components": [], "telegram": {}}
        with pytest.raises(SystemExit) as exc_info:
            run_watchdog(cfg)
        assert exc_info.value.code == 1


class TestRunnerIntegration:
    """Integration: runner + watchdog + heartbeat writer."""

    def test_detects_healthy_heartbeat(self, tmp_path):
        """Runner sees a fresh heartbeat as healthy."""
        from core.heartbeat_writer import HeartbeatWriter

        hb_path = tmp_path / "hb.json"
        writer = HeartbeatWriter(hb_path, component="test-comp")
        writer.write(status="healthy")

        cfg = {
            "components": [
                {
                    "name": "test-comp",
                    "heartbeat_path": str(hb_path),
                    "stale_threshold_seconds": 120,
                    "cooldown_seconds": 0,
                }
            ],
            "telegram": {},
        }

        mock_sink = MagicMock()
        with patch("core.watchdog_runner._build_sinks", return_value=[mock_sink]):
            run_watchdog(cfg, once=True)

        # No alerts for healthy component
        mock_sink.send.assert_not_called()

    def test_detects_missing_heartbeat(self, tmp_path):
        """Runner alerts on missing heartbeat file."""
        cfg = {
            "components": [
                {
                    "name": "missing-comp",
                    "heartbeat_path": str(tmp_path / "nonexistent.json"),
                    "stale_threshold_seconds": 120,
                    "cooldown_seconds": 0,
                }
            ],
            "telegram": {},
        }

        mock_sink = MagicMock()
        with patch("core.watchdog_runner._build_sinks", return_value=[mock_sink]):
            run_watchdog(cfg, once=True)

        mock_sink.send.assert_called_once()
        alert = mock_sink.send.call_args[0][0]
        assert alert.component == "missing-comp"
        assert "missing" in alert.message.lower()
