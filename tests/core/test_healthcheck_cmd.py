import json
import os
import time

from core.healthcheck_cmd import main


class TestHealthcheckCmd:
    def _write_heartbeat(
        self,
        path: str,
        status: str = "healthy",
        timestamp_unix: float | None = None,
    ) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        data = {
            "component": "legacy",
            "status": status,
            "timestamp_unix": timestamp_unix or time.time(),
        }
        with open(path, "w") as f:
            json.dump(data, f)

    def test_healthy_when_fresh_valid_heartbeat(self, tmp_path, monkeypatch):
        hb_path = tmp_path / "storage" / "heartbeat.json"
        self._write_heartbeat(str(hb_path))
        monkeypatch.chdir(tmp_path)
        assert main() == 0

    def test_unhealthy_when_heartbeat_missing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert main() == 1

    def test_unhealthy_when_heartbeat_malformed(self, tmp_path, monkeypatch):
        hb_path = tmp_path / "storage" / "heartbeat.json"
        hb_path.parent.mkdir(parents=True, exist_ok=True)
        hb_path.write_text("not-json")
        monkeypatch.chdir(tmp_path)
        assert main() == 1

    def test_unhealthy_when_heartbeat_stale(self, tmp_path, monkeypatch):
        hb_path = tmp_path / "storage" / "heartbeat.json"
        # 200 seconds ago — exceeds 120s threshold
        self._write_heartbeat(str(hb_path), timestamp_unix=time.time() - 200)
        monkeypatch.chdir(tmp_path)
        assert main() == 1

    def test_unhealthy_when_status_is_error(self, tmp_path, monkeypatch):
        hb_path = tmp_path / "storage" / "heartbeat.json"
        self._write_heartbeat(str(hb_path), status="error")
        monkeypatch.chdir(tmp_path)
        assert main() == 1

    def test_healthy_when_status_running(self, tmp_path, monkeypatch):
        hb_path = tmp_path / "storage" / "heartbeat.json"
        self._write_heartbeat(str(hb_path), status="running")
        monkeypatch.chdir(tmp_path)
        assert main() == 0

    def test_healthy_when_status_healthy(self, tmp_path, monkeypatch):
        hb_path = tmp_path / "storage" / "heartbeat.json"
        self._write_heartbeat(str(hb_path), status="healthy")
        monkeypatch.chdir(tmp_path)
        assert main() == 0
