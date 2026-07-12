"""Shared read-only enforcement for mutating Rainbow routes.

Rainbow is a TA-signal evidence source and must never accept writes while
``RainbowSettings.read_only`` is true. Mirrors the module-level-settings
pattern already used by ``rainbow.distribution.api``.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

_settings: Any = None


def configure(settings: Any) -> None:
    """Bind the active settings instance. Called once at app startup."""
    global _settings
    _settings = settings


def require_write_enabled() -> None:
    """FastAPI dependency: reject mutating requests while Rainbow is read-only."""
    if _settings is not None and getattr(_settings, "read_only", False):
        raise HTTPException(status_code=405, detail="Rainbow is running in read-only mode")
