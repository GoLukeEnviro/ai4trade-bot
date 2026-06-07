from __future__ import annotations

import json
import logging

log = logging.getLogger(__name__)


def clamp_score(score: float, min_val: float = -1.0, max_val: float = 1.0) -> float:
    """Score auf [min_val, max_val] begrenzen."""
    return max(min_val, min(max_val, score))


def clamp_confidence(confidence: float) -> float:
    """Confidence auf [0.0, 1.0] begrenzen."""
    return max(0.0, min(1.0, confidence))


def safe_json_parse(text: str) -> dict | None:
    """JSON sicher parsen, None bei Fehler."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
