from __future__ import annotations

from typing import Any


def summarize_raw_data(raw_data: dict[str, Any] | None, max_keys: int = 8) -> str:
    if not raw_data:
        return "No technical data available."
    parts = [f"{k}={v}" for k, v in list(raw_data.items())[:max_keys]]
    return ", ".join(parts)
