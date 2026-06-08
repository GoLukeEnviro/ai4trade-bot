import json
import time

from core.heartbeat_writer import HeartbeatWriter, read_heartbeat


class TestHeartbeatWriter:
    def test_write_creates_valid_json_file(self, tmp_path):
        hb = HeartbeatWriter(tmp_path / "hb.json", component="legacy")
        data = hb.write()
        raw = (tmp_path / "hb.json").read_text()
        parsed = json.loads(raw)
        assert parsed["component"] == "legacy"
        assert parsed["status"] == "healthy"
        assert "timestamp_unix" in parsed
        assert data == parsed

    def test_write_is_atomic(self, tmp_path):
        hb = HeartbeatWriter(tmp_path / "hb.json", component="legacy")
        hb.write()
        # No leftover .tmp file after successful write
        assert not (tmp_path / "hb.tmp").exists()
        assert (tmp_path / "hb.json").exists()

    def test_write_count_increments(self, tmp_path):
        hb = HeartbeatWriter(tmp_path / "hb.json", component="legacy")
        assert hb.write_count == 0
        hb.write()
        assert hb.write_count == 1
        hb.write()
        assert hb.write_count == 2

    def test_uptime_seconds_increases(self, tmp_path):
        hb = HeartbeatWriter(tmp_path / "hb.json", component="legacy")
        d1 = hb.write()
        time.sleep(0.15)
        d2 = hb.write()
        assert d2["uptime_seconds"] > d1["uptime_seconds"]

    def test_extra_fields_merged(self, tmp_path):
        hb = HeartbeatWriter(
            tmp_path / "hb.json",
            component="legacy",
            extra={"env": "prod"},
        )
        data = hb.write()
        assert data["env"] == "prod"

        # extra_fields via kwargs
        data2 = hb.write(custom="value")
        assert data2["custom"] == "value"
        assert data2["env"] == "prod"

    def test_parent_directory_auto_created(self, tmp_path):
        deep = tmp_path / "a" / "b" / "c" / "hb.json"
        hb = HeartbeatWriter(deep, component="legacy")
        hb.write()
        assert deep.exists()

    def test_status_field_correct(self, tmp_path):
        hb = HeartbeatWriter(tmp_path / "hb.json", component="legacy")
        data = hb.write(status="running")
        assert data["status"] == "running"

    def test_timestamp_is_iso_format(self, tmp_path):
        hb = HeartbeatWriter(tmp_path / "hb.json", component="legacy")
        data = hb.write()
        ts = data["timestamp"]
        # Should contain 'T' separator and timezone
        assert "T" in ts
        assert "+" in ts or "Z" in ts

    def test_multiple_writes_update_file(self, tmp_path):
        hb = HeartbeatWriter(tmp_path / "hb.json", component="legacy")
        hb.write()
        raw1 = (tmp_path / "hb.json").read_text()
        time.sleep(0.05)
        hb.write()
        raw2 = (tmp_path / "hb.json").read_text()
        assert raw1 != raw2

    def test_write_count_in_file(self, tmp_path):
        hb = HeartbeatWriter(tmp_path / "hb.json", component="legacy")
        hb.write()
        hb.write()
        data = hb.write()
        assert data["write_count"] == 2

    def test_path_property(self, tmp_path):
        p = tmp_path / "hb.json"
        hb = HeartbeatWriter(p, component="legacy")
        assert hb.path == p


class TestReadHeartbeat:
    def test_returns_none_for_missing_file(self, tmp_path):
        assert read_heartbeat(tmp_path / "missing.json") is None

    def test_returns_none_for_malformed_json(self, tmp_path):
        p = tmp_path / "hb.json"
        p.write_text("not json{{{")
        assert read_heartbeat(p) is None

    def test_returns_none_for_non_dict_json(self, tmp_path):
        p = tmp_path / "hb.json"
        p.write_text("[1, 2, 3]")
        assert read_heartbeat(p) is None

    def test_returns_none_for_dict_without_timestamp_unix(self, tmp_path):
        p = tmp_path / "hb.json"
        p.write_text(json.dumps({"status": "healthy"}))
        assert read_heartbeat(p) is None

    def test_reads_valid_heartbeat(self, tmp_path):
        hb = HeartbeatWriter(tmp_path / "hb.json", component="legacy")
        hb.write()
        data = read_heartbeat(tmp_path / "hb.json")
        assert data is not None
        assert data["component"] == "legacy"
        assert "timestamp_unix" in data
