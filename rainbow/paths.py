"""Canonical runtime paths shared between the heartbeat writer and /health.

Kept in one place so the writer and the reader can never drift apart again
(see docs/reports/runtime-health-watchdog-report.md for the historical
mismatch between ``storage/...`` and ``rainbow/storage/...``).
"""

from __future__ import annotations

HEARTBEAT_PATH = "rainbow/storage/heartbeat_rainbow.json"
