"""Tests for core.watchdog — heartbeat file monitoring with cooldown and notification abstraction."""

import json
import time
from unittest.mock import MagicMock

from core.watchdog import (
    LogNotificationSink,
    Watchdog,
    WatchdogAlert,
    WatchdogSeverity,
    WatchedComponent,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_heartbeat(path, *, timestamp=None, status="healthy", extra=None):
    """Write a valid heartbeat JSON file."""
    data = {"timestamp_unix": timestamp or time.time(), "status": status}
    if extra:
        data.update(extra)
    path.write_text(json.dumps(data))


def _make_component(name, path, *, stale_threshold=120.0, cooldown=300.0):
    return WatchedComponent(
        name=name, heartbeat_path=path, stale_threshold_seconds=stale_threshold, cooldown_seconds=cooldown
    )


# ---------------------------------------------------------------------------
# Detection tests
# ---------------------------------------------------------------------------


class TestMissingFile:
    def test_missing_heartbeat_returns_critical(self, tmp_path):
        comp = _make_component("svc", tmp_path / "missing.json")
        wd = Watchdog([comp], sinks=[LogNotificationSink()])
        alerts = wd.check_all()
        assert len(alerts) == 1
        assert alerts[0].severity == WatchdogSeverity.CRITICAL
        assert "missing" in alerts[0].message.lower()


class TestMalformedJson:
    def test_invalid_json_returns_critical(self, tmp_path):
        hb = tmp_path / "bad.json"
        hb.write_text("not json at all {{{")
        comp = _make_component("svc", hb)
        wd = Watchdog([comp], sinks=[LogNotificationSink()])
        alerts = wd.check_all()
        assert len(alerts) == 1
        assert alerts[0].severity == WatchdogSeverity.CRITICAL
        assert "malformed" in alerts[0].message.lower()

    def test_non_dict_json_returns_critical(self, tmp_path):
        hb = tmp_path / "list.json"
        hb.write_text(json.dumps([1, 2, 3]))
        comp = _make_component("svc", hb)
        wd = Watchdog([comp], sinks=[LogNotificationSink()])
        alerts = wd.check_all()
        assert len(alerts) == 1
        assert alerts[0].severity == WatchdogSeverity.CRITICAL
        assert "timestamp_unix" in alerts[0].message

    def test_dict_without_timestamp_returns_critical(self, tmp_path):
        hb = tmp_path / "no_ts.json"
        hb.write_text(json.dumps({"status": "healthy"}))
        comp = _make_component("svc", hb)
        wd = Watchdog([comp], sinks=[LogNotificationSink()])
        alerts = wd.check_all()
        assert len(alerts) == 1
        assert alerts[0].severity == WatchdogSeverity.CRITICAL
        assert "timestamp_unix" in alerts[0].message


class TestStaleHeartbeat:
    def test_stale_heartbeat_returns_warning(self, tmp_path):
        hb = tmp_path / "stale.json"
        _write_heartbeat(hb, timestamp=time.time() - 200)
        comp = _make_component("svc", hb, stale_threshold=120.0)
        wd = Watchdog([comp], sinks=[LogNotificationSink()])
        alerts = wd.check_all()
        assert len(alerts) == 1
        assert alerts[0].severity == WatchdogSeverity.WARNING
        assert "stale" in alerts[0].message.lower()

    def test_fresh_heartbeat_no_alert(self, tmp_path):
        hb = tmp_path / "fresh.json"
        _write_heartbeat(hb, timestamp=time.time() - 10)
        comp = _make_component("svc", hb, stale_threshold=120.0)
        wd = Watchdog([comp], sinks=[LogNotificationSink()])
        alerts = wd.check_all()
        assert alerts == []


class TestUnhealthyStatus:
    def test_unhealthy_status_returns_warning(self, tmp_path):
        hb = tmp_path / "unhealthy.json"
        _write_heartbeat(hb, status="error")
        comp = _make_component("svc", hb)
        wd = Watchdog([comp], sinks=[LogNotificationSink()])
        alerts = wd.check_all()
        assert len(alerts) == 1
        assert alerts[0].severity == WatchdogSeverity.WARNING
        assert "unhealthy status" in alerts[0].message.lower()

    def test_healthy_status_no_alert(self, tmp_path):
        hb = tmp_path / "healthy.json"
        _write_heartbeat(hb, status="healthy")
        comp = _make_component("svc", hb)
        wd = Watchdog([comp], sinks=[LogNotificationSink()])
        assert wd.check_all() == []

    def test_running_status_no_alert(self, tmp_path):
        hb = tmp_path / "running.json"
        _write_heartbeat(hb, status="running")
        comp = _make_component("svc", hb)
        wd = Watchdog([comp], sinks=[LogNotificationSink()])
        assert wd.check_all() == []


# ---------------------------------------------------------------------------
# Cooldown tests
# ---------------------------------------------------------------------------


class TestCooldown:
    def test_cooldown_suppresses_repeated_alerts(self, tmp_path):
        hb = tmp_path / "missing.json"
        # File doesn't exist → alert every time unless cooldown blocks it
        comp = _make_component("svc", hb, cooldown=300.0)
        wd = Watchdog([comp], sinks=[LogNotificationSink()])

        first = wd.check_all()
        assert len(first) == 1

        second = wd.check_all()
        assert second == []  # suppressed by cooldown

    def test_cooldown_allows_alert_after_period(self, tmp_path):
        hb = tmp_path / "missing.json"
        comp = _make_component("svc", hb, cooldown=0.0)  # no cooldown
        wd = Watchdog([comp], sinks=[LogNotificationSink()])

        first = wd.check_all()
        assert len(first) == 1

        second = wd.check_all()
        assert len(second) == 1  # no cooldown → not suppressed


# ---------------------------------------------------------------------------
# Notification sink tests
# ---------------------------------------------------------------------------


class TestNotificationSinks:
    def test_multiple_sinks_all_receive_alerts(self, tmp_path):
        hb = tmp_path / "missing.json"
        comp = _make_component("svc", hb)
        sink_a = MagicMock()
        sink_b = MagicMock()
        wd = Watchdog([comp], sinks=[sink_a, sink_b])
        wd.check_all()
        assert sink_a.send.call_count == 1
        assert sink_b.send.call_count == 1

    def test_sink_exception_is_caught(self, tmp_path):
        hb = tmp_path / "missing.json"
        comp = _make_component("svc", hb)
        bad_sink = MagicMock()
        bad_sink.send.side_effect = RuntimeError("boom")
        good_sink = MagicMock()
        wd = Watchdog([comp], sinks=[bad_sink, good_sink])
        # Should not raise
        alerts = wd.check_all()
        assert len(alerts) == 1
        # Good sink should still be called (order: bad first, then good)
        good_sink.send.assert_called_once()

    def test_custom_sink_protocol_implementation(self, tmp_path):
        """Verify a hand-rolled NotificationSink works via duck-typing."""

        class Collector:
            def __init__(self):
                self.alerts: list[WatchdogAlert] = []

            def send(self, alert: WatchdogAlert) -> None:
                self.alerts.append(alert)

        hb = tmp_path / "missing.json"
        comp = _make_component("svc", hb)
        collector = Collector()
        wd = Watchdog([comp], sinks=[collector])
        alerts = wd.check_all()
        assert len(alerts) == 1
        assert len(collector.alerts) == 1
        assert collector.alerts[0].component == "svc"


# ---------------------------------------------------------------------------
# Alert history tests
# ---------------------------------------------------------------------------


class TestAlertHistory:
    def test_alert_history_tracked(self, tmp_path):
        hb = tmp_path / "missing.json"
        comp = _make_component("svc", hb, cooldown=0.0)
        wd = Watchdog([comp], sinks=[LogNotificationSink()])
        wd.check_all()
        wd.check_all()
        assert len(wd.alert_history) == 2

    def test_alert_history_returns_copy(self, tmp_path):
        hb = tmp_path / "missing.json"
        comp = _make_component("svc", hb, cooldown=0.0)
        wd = Watchdog([comp], sinks=[LogNotificationSink()])
        wd.check_all()
        history = wd.alert_history
        history.clear()
        assert len(wd.alert_history) == 1  # original unaffected

    def test_clear_history(self, tmp_path):
        hb = tmp_path / "missing.json"
        comp = _make_component("svc", hb, cooldown=0.0)
        wd = Watchdog([comp], sinks=[LogNotificationSink()])
        wd.check_all()
        assert len(wd.alert_history) == 1
        wd.clear_history()
        assert len(wd.alert_history) == 0


# ---------------------------------------------------------------------------
# Multi-component tests
# ---------------------------------------------------------------------------


class TestMultipleComponents:
    def test_independent_checks(self, tmp_path):
        good_hb = tmp_path / "good.json"
        bad_hb = tmp_path / "bad.json"
        _write_heartbeat(good_hb, status="healthy")
        bad_hb.write_text("not json")

        comps = [
            _make_component("good_svc", good_hb),
            _make_component("bad_svc", bad_hb),
        ]
        wd = Watchdog(comps, sinks=[LogNotificationSink()])
        alerts = wd.check_all()
        assert len(alerts) == 1
        assert alerts[0].component == "bad_svc"

    def test_custom_stale_threshold_per_component(self, tmp_path):
        hb = tmp_path / "hb.json"
        _write_heartbeat(hb, timestamp=time.time() - 30)

        comps = [
            _make_component("strict", hb, stale_threshold=10.0),
            _make_component("lenient", hb, stale_threshold=60.0),
        ]
        wd = Watchdog(comps, sinks=[LogNotificationSink()])
        alerts = wd.check_all()
        assert len(alerts) == 1
        assert alerts[0].component == "strict"


# ---------------------------------------------------------------------------
# LogNotificationSink unit test
# ---------------------------------------------------------------------------


class TestLogNotificationSink:
    def test_critical_logs_error(self, caplog):
        sink = LogNotificationSink()
        alert = WatchdogAlert(component="x", severity=WatchdogSeverity.CRITICAL, message="boom")
        with caplog.at_level("ERROR"):
            sink.send(alert)
        assert "CRITICAL" in caplog.text

    def test_warning_logs_warning(self, caplog):
        sink = LogNotificationSink()
        alert = WatchdogAlert(component="x", severity=WatchdogSeverity.WARNING, message="soft")
        with caplog.at_level("WARNING"):
            sink.send(alert)
        assert "WARNING" in caplog.text

    def test_info_logs_info(self, caplog):
        sink = LogNotificationSink()
        alert = WatchdogAlert(component="x", severity=WatchdogSeverity.INFO, message="fyi")
        with caplog.at_level("INFO"):
            sink.send(alert)
        assert "INFO" in caplog.text
