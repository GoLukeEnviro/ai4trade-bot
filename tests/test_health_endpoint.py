# tests/test_health_endpoint.py
"""Tests for the legacy health/metrics HTTP endpoint on port 9090."""

import json
import threading
import time
from http.server import HTTPServer
from socketserver import ThreadingMixIn

from core.metrics import get_metrics


def _find_free_port() -> int:
    """Find a free port to avoid conflicts during tests."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def _start_test_server(port: int):
    import main

    main._bot_start_time = time.time()
    from main import HealthHandler

    server = ThreadedHTTPServer(("127.0.0.1", port), HealthHandler)
    return server


class TestHealthHandler:
    """Test the HealthHandler HTTP endpoint."""

    def test_health_endpoint_returns_json(self):
        import urllib.request

        port = _find_free_port()
        server = _start_test_server(port)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        time.sleep(0.2)

        try:
            resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/health")
            assert resp.status == 200
            data = json.loads(resp.read().decode())
            assert data["status"] == "healthy"
            assert "uptime_seconds" in data
            assert isinstance(data["uptime_seconds"], (int, float))
        finally:
            server.shutdown()

    def test_metrics_endpoint_returns_prometheus(self):
        import urllib.request

        port = _find_free_port()
        server = _start_test_server(port)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        time.sleep(0.2)

        try:
            resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics")
            assert resp.status == 200
            content = resp.read().decode()
            # Should contain Prometheus metric names
            assert "bot_signals_total" in content or "bot_" in content
        finally:
            server.shutdown()

    def test_unknown_path_returns_404(self):
        import urllib.error
        import urllib.request

        port = _find_free_port()
        server = _start_test_server(port)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        time.sleep(0.2)

        try:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/nonexistent")
                assert False, "Should have raised HTTPError"
            except urllib.error.HTTPError as e:
                assert e.code == 404
        finally:
            server.shutdown()


class TestGetMetrics:
    """Test that get_metrics() returns valid Prometheus output."""

    def test_get_metrics_contains_signal_counters(self):
        data = get_metrics().decode()
        assert "bot_signals_total" in data
        assert "bot_signals_published_total" in data

    def test_get_metrics_contains_last_signal_timestamp(self):
        data = get_metrics().decode()
        assert "bot_last_signal_timestamp_seconds" in data
