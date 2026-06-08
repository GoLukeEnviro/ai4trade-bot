"""CLI health check command for Legacy Docker container.

Exit 0 if healthy, exit 1 if unhealthy.
Checks:
1. Heartbeat file exists and is fresh (not stale)
2. Heartbeat file is valid JSON
3. Optional: database file exists
"""

import json
import sys
import time
from pathlib import Path


def main() -> int:
    """Run health check. Returns 0 for healthy, 1 for unhealthy."""
    heartbeat_path = Path("storage/heartbeat.json")
    stale_threshold_seconds = 120  # 2 minutes

    # Check 1: file exists
    if not heartbeat_path.exists():
        print(f"UNHEALTHY: heartbeat file missing: {heartbeat_path}")
        return 1

    # Check 2: parse JSON
    try:
        data = json.loads(heartbeat_path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        print(f"UNHEALTHY: heartbeat malformed: {e}")
        return 1

    # Check 3: not stale
    ts = data.get("timestamp_unix", 0)
    age = time.time() - ts
    if age > stale_threshold_seconds:
        print(f"UNHEALTHY: heartbeat stale ({age:.0f}s old, threshold={stale_threshold_seconds}s)")
        return 1

    # Check 4: status field
    status = data.get("status", "unknown")
    if status not in ("healthy", "running"):
        print(f"UNHEALTHY: status={status}")
        return 1

    print(f"HEALTHY: age={age:.0f}s, status={status}, component={data.get('component', '?')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
