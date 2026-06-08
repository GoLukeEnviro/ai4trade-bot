"""Rule-based review policy — deterministic handling decisions."""

from __future__ import annotations

from core.signals.envelope import CanonicalSignalEnvelope
from rainbow.evaluation.models import AIEvaluation


class ReviewPolicy:
    """Deterministic review policy that decides final signal handling.

    Rules are applied in strict priority order.  Deterministic risk /
    data-quality gates always take precedence over LLM recommendations.
    """

    def decide(
        self,
        evaluation: AIEvaluation,
        envelope: CanonicalSignalEnvelope,
    ) -> str:
        """Return the final handling string.

        Returns one of: ``"store_only"``, ``"summary"``,
        ``"risk_summary"``, ``"review_required"``, ``"suppress"``.
        """
        # Rule 1 — data quality gate
        if envelope.data_quality.status != "ok":
            return "review_required"

        # Rule 2 — high risk gate
        if envelope.risk_score >= 0.75:
            return "risk_summary"

        # Rule 3 — contradictory signal
        if evaluation.signal_quality == "contradictory":
            return "review_required"

        # Rule 4 — suppress directive
        if evaluation.recommended_handling == "suppress":
            return "suppress"

        # Rule 5 — trust LLM recommendation when confidence is high
        if (
            evaluation.ai_confidence >= 0.7
            and evaluation.recommended_handling in {"summary", "risk_summary"}
        ):
            return evaluation.recommended_handling

        # Rule 6 — default
        return "store_only"
