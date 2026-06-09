"""FastAPI router for the Rainbow signal ingest endpoint."""

from __future__ import annotations

import logging

from fastapi import APIRouter

from rainbow.ingest.ingest import RainbowIngestor
from rainbow.ingest.models import RainbowIngestRequest, RainbowIngestResult

log = logging.getLogger("rainbow.ingest.router")

router = APIRouter(prefix="/api/v1/signals", tags=["ingest"])

# The ingestor instance is set at app-startup via ``init_ingest_router``.
_ingestor: RainbowIngestor | None = None


def init_ingest_router(ingestor: RainbowIngestor) -> None:
    """Bind a :class:`RainbowIngestor` instance to the router.

    Must be called once during application startup, before any request
    hits the ingest endpoint.
    """
    global _ingestor  # noqa: PLW0603
    _ingestor = ingestor


@router.post("/ingest", response_model=RainbowIngestResult)
async def ingest_signal(body: RainbowIngestRequest) -> RainbowIngestResult:
    """Accept an external signal and persist it in the canonical registry.

    This endpoint is **data-only** — it never triggers trade execution.
    All ingested signals have ``can_execute=False`` and ``dry_run_only=True``.
    """
    if _ingestor is None:
        return RainbowIngestResult(status="error", reason="ingestor_not_initialized")

    # RainbowIngestor.ingest never raises — all errors map to status="error"
    return _ingestor.ingest(body)
