import json
import logging
import time
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


class HeartbeatWriter:
    """Writes a JSON heartbeat file at regular intervals.

    Each write contains: timestamp (ISO), timestamp_unix, uptime_seconds,
    status, component, extra fields.  The file is written atomically
    (write to .tmp, then rename).
    """

    def __init__(
        self,
        path: str | Path,
        component: str,
        extra: dict[str, Any] | None = None,
    ):
        self._path = Path(path)
        self._component = component
        self._extra = extra or {}
        self._start_time = time.monotonic()
        self._write_count = 0
        # Ensure parent dir exists
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, status: str = "healthy", **extra_fields: Any) -> dict:
        """Write heartbeat file atomically."""
        now = time.time()
        data = {
            "component": self._component,
            "status": status,
            "timestamp": _isoformat(now),
            "timestamp_unix": now,
            "uptime_seconds": round(time.monotonic() - self._start_time, 1),
            "write_count": self._write_count,
            **self._extra,
            **extra_fields,
        }
        tmp_path = self._path.with_suffix(".tmp")
        try:
            tmp_path.write_text(json.dumps(data, indent=2) + "\n")
            tmp_path.rename(self._path)
            self._write_count += 1
        except OSError as e:
            log.warning("Failed to write heartbeat to %s: %s", self._path, e)
        return data

    @property
    def path(self) -> Path:
        return self._path

    @property
    def write_count(self) -> int:
        return self._write_count


def _isoformat(unix_ts: float) -> str:
    from datetime import UTC, datetime

    return datetime.fromtimestamp(unix_ts, tz=UTC).isoformat()


def read_heartbeat(path: str | Path) -> dict | None:
    """Read and parse a heartbeat file. Returns None if missing or malformed."""
    p = Path(path)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
        if not isinstance(data, dict) or "timestamp_unix" not in data:
            return None
        return data
    except (json.JSONDecodeError, OSError):
        return None
