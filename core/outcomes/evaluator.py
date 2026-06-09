"""Outcome evaluator — compares past signals against price movement.

This module is purely observational. It never triggers trades, strategy changes,
or parameter modulation. It evaluates signals and records outcomes for training.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from core.outcomes.model import OutcomeLabel, SignalOutcome
from core.outcomes.price_provider import PriceProvider
from core.outcomes.repository import OutcomeRepository

log = logging.getLogger(__name__)


class OutcomeEvaluator:
    """Evaluate past canonical signals against actual price movement.

    Parameters
    ----------
    outcome_repo : OutcomeRepository
        Where to persist outcome records.
    price_provider : PriceProvider
        Source of price data for evaluation.
    evaluation_window_seconds : int
        How far into the future to look for price movement.
    min_move_pct : float
        Minimum % price move to count as win/loss (not neutral).
    """

    def __init__(
        self,
        outcome_repo: OutcomeRepository,
        price_provider: PriceProvider,
        evaluation_window_seconds: int = 3600,
        min_move_pct: float = 0.5,
    ) -> None:
        self._repo = outcome_repo
        self._prices = price_provider
        self._window_seconds = evaluation_window_seconds
        self._min_move_pct = min_move_pct

    def evaluate_signal(self, signal_data: dict[str, Any]) -> SignalOutcome | None:
        """Evaluate a single canonical signal against price movement.

        Parameters
        ----------
        signal_data : dict
            A row from the canonical signal registry, containing at minimum:
            id, asset, direction (bullish/bearish/neutral), signal_class,
            created_at, confidence, source.

        Returns
        -------
        SignalOutcome or None
            The outcome, or None if evaluation is impossible (e.g. missing price).
        """
        signal_id = signal_data.get("id") or signal_data.get("signal_id", "")
        if not signal_id:
            log.warning("Signal has no id — skipping")
            return None

        # Idempotency: skip if already evaluated
        if self._repo.has_outcome(signal_id):
            log.debug("Signal %s already has outcome — skipping", signal_id)
            return None

        asset = signal_data.get("asset", "")
        direction = signal_data.get("direction", "neutral")
        signal_class = signal_data.get("signal_class", "")
        source = signal_data.get("source", "")
        confidence = signal_data.get("confidence")

        # Parse emitted_at timestamp
        emitted_at = self._parse_dt(signal_data.get("created_at", ""))
        if emitted_at is None:
            log.warning("Signal %s has no valid created_at — skipping", signal_id)
            return None

        # Fetch entry price (at signal time)
        entry_price = self._prices.get_price(asset, emitted_at)
        if entry_price is None or entry_price <= 0:
            log.info("No valid entry price for %s at %s — recording unknown", asset, emitted_at)
            return self._build_outcome(
                signal_id=signal_id,
                asset=asset,
                direction=direction,
                signal_class=signal_class,
                source=source,
                emitted_at=emitted_at,
                confidence=confidence,
                entry_price=None,
                outcome_price=None,
                outcome_label=OutcomeLabel.UNKNOWN,
                outcome_score=0.0,
                reason="no_entry_price",
            )

        # Fetch outcome price (at evaluation window end)
        eval_time = emitted_at + timedelta(seconds=self._window_seconds)
        outcome_price = self._prices.get_price(asset, eval_time)
        if outcome_price is None or outcome_price <= 0:
            log.info("No valid outcome price for %s at %s — recording unknown", asset, eval_time)
            return self._build_outcome(
                signal_id=signal_id,
                asset=asset,
                direction=direction,
                signal_class=signal_class,
                source=source,
                emitted_at=emitted_at,
                confidence=confidence,
                entry_price=entry_price,
                outcome_price=None,
                outcome_label=OutcomeLabel.UNKNOWN,
                outcome_score=0.0,
                reason="no_outcome_price",
            )

        # Compute price change
        price_change_pct = ((outcome_price - entry_price) / entry_price) * 100.0

        # Determine outcome label
        label, score, reason = self._classify(
            direction=direction,
            price_change_pct=price_change_pct,
        )

        return self._build_outcome(
            signal_id=signal_id,
            asset=asset,
            direction=direction,
            signal_class=signal_class,
            source=source,
            emitted_at=emitted_at,
            confidence=confidence,
            entry_price=entry_price,
            outcome_price=outcome_price,
            outcome_label=label,
            outcome_score=score,
            reason=reason,
            price_change_pct=price_change_pct,
        )

    def evaluate_batch(
        self,
        signals: list[dict[str, Any]],
        *,
        dry_run: bool = False,
    ) -> dict[str, int]:
        """Evaluate a batch of signals.

        Returns a summary dict with counts: evaluated, skipped, errors.
        """
        stats = {"evaluated": 0, "skipped": 0, "errors": 0}
        for sig in signals:
            try:
                outcome = self.evaluate_signal(sig)
                if outcome is None:
                    stats["skipped"] += 1
                    continue
                if not dry_run:
                    self._repo.upsert(outcome)
                stats["evaluated"] += 1
                log.info(
                    "Evaluated %s → %s (%.2f%%) [%s]",
                    outcome.signal_id[:8],
                    outcome.outcome_label.value,
                    outcome.price_change_pct or 0.0,
                    outcome.reason,
                )
            except Exception as e:
                log.error("Error evaluating signal %s: %s", sig.get("id", "?"), e)
                stats["errors"] += 1
        return stats

    # ------------------------------------------------------------------
    # Classification logic
    # ------------------------------------------------------------------

    def _classify(
        self,
        direction: str,
        price_change_pct: float,
    ) -> tuple[OutcomeLabel, float, str]:
        """Classify an outcome based on direction and price change.

        Returns (label, score, reason).
        Score: +1.0 for strong win, -1.0 for strong loss, 0.0 for neutral/unknown.
        """
        abs_move = abs(price_change_pct)

        if direction in ("bullish",):
            if price_change_pct >= self._min_move_pct:
                score = min(1.0, abs_move / (self._min_move_pct * 3))
                return OutcomeLabel.WIN, score, "price_moved_up"
            elif price_change_pct <= -self._min_move_pct:
                score = max(-1.0, -abs_move / (self._min_move_pct * 3))
                return OutcomeLabel.LOSS, score, "price_moved_down"
            else:
                return OutcomeLabel.NEUTRAL, 0.0, "insufficient_move"

        elif direction in ("bearish",):
            if price_change_pct <= -self._min_move_pct:
                score = min(1.0, abs_move / (self._min_move_pct * 3))
                return OutcomeLabel.WIN, score, "price_moved_down"
            elif price_change_pct >= self._min_move_pct:
                score = max(-1.0, -abs_move / (self._min_move_pct * 3))
                return OutcomeLabel.LOSS, score, "price_moved_up"
            else:
                return OutcomeLabel.NEUTRAL, 0.0, "insufficient_move"

        else:  # neutral or unknown direction
            return OutcomeLabel.NEUTRAL, 0.0, "no_directional_bias"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_outcome(
        self,
        signal_id: str,
        asset: str,
        direction: str,
        signal_class: str,
        source: str,
        emitted_at: datetime,
        confidence: float | None,
        entry_price: float | None,
        outcome_price: float | None,
        outcome_label: OutcomeLabel,
        outcome_score: float,
        reason: str,
        price_change_pct: float | None = None,
    ) -> SignalOutcome:
        return SignalOutcome(
            signal_id=signal_id,
            asset=asset,
            direction=direction,
            signal_class=signal_class,
            source=source,
            emitted_at=emitted_at,
            evaluation_window_seconds=self._window_seconds,
            entry_price=entry_price,
            outcome_price=outcome_price,
            price_change_pct=price_change_pct,
            expected_direction=direction,
            outcome_label=outcome_label,
            outcome_score=outcome_score,
            reason=reason,
            confidence_at_signal=confidence,
        )

    @staticmethod
    def _parse_dt(val: Any) -> datetime | None:
        """Parse a datetime from various formats."""
        if isinstance(val, datetime):
            return val
        if not val:
            return None
        try:
            return datetime.fromisoformat(str(val))
        except (ValueError, TypeError):
            return None
