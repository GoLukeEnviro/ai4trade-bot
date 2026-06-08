"""Compact signal summariser for notifications and downstream consumers."""

from __future__ import annotations

from core.signals.envelope import CanonicalSignalEnvelope
from rainbow.evaluation.models import AIEvaluation

_MAX_LEN = 280


def format_signal_summary(
    envelope: CanonicalSignalEnvelope,
    evaluation: AIEvaluation | None = None,
) -> str:
    """Return a compact human-readable summary (≤280 chars).

    Example output::

        [BTC/USDT] ENTRY bullish (conf: 0.72, risk: 0.35) —
        Reason: RSI oversold + volume spike. Quality: strong.
    """
    sig_class = envelope.signal_class.value.upper()
    direction = envelope.direction.value
    asset = envelope.asset
    conf = envelope.confidence
    risk = envelope.risk_score

    # Build detail string from evaluation if present
    detail = ""
    if evaluation is not None:
        reason = evaluation.summary or evaluation.reasoning
        quality = evaluation.signal_quality
        if reason:
            detail = f" Reason: {reason}. Quality: {quality}."
        else:
            detail = f" Quality: {quality}."

    base = f"[{asset}] {sig_class} {direction} (conf: {conf:.2f}, risk: {risk:.2f})"

    # Truncate detail to fit within MAX_LEN
    budget = _MAX_LEN - len(base)
    if detail and len(detail) > budget:
        detail = detail[: max(budget - 1, 0)] + "…"

    summary = base + detail
    return summary[:_MAX_LEN]
