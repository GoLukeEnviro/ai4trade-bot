# core/outcome_tracker.py
"""Background outcome tracker for self-improvement.

Checks pending signals after OUTCOME_WINDOW_HOURS and evaluates whether
the BUY/SELL signal was correct based on actual price movement.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from storage.sqlite_repository import SqliteSignalRepository

log = logging.getLogger(__name__)


class OutcomeTracker:
    """Background thread that evaluates signal outcomes after a configurable window."""

    def __init__(
        self,
        repository: SqliteSignalRepository,
        outcome_window_hours: float | None = None,
        check_interval_seconds: float = 300.0,
        get_price_fn=None,
    ) -> None:
        self._repo = repository
        self._window_hours = outcome_window_hours or float(os.getenv("OUTCOME_WINDOW_HOURS", "4"))
        self._check_interval = check_interval_seconds
        self._get_price_fn = get_price_fn or self._default_get_price
        self._shutdown = threading.Event()

    def start(self) -> None:
        """Start the background tracker thread."""
        t = threading.Thread(target=self._run_loop, daemon=True, name="outcome_tracker")
        t.start()
        log.info(
            "OutcomeTracker gestartet (window=%dh, interval=%.0fs)",
            self._window_hours,
            self._check_interval,
        )

    def stop(self) -> None:
        """Signal the tracker to stop."""
        self._shutdown.set()

    def _run_loop(self) -> None:
        while not self._shutdown.is_set():
            try:
                self._check_outcomes()
            except Exception as exc:
                log.error("OutcomeTracker Fehler: %s", exc)
            self._shutdown.wait(timeout=self._check_interval)

    def _check_outcomes(self) -> None:
        pending = self._repo.get_pending_outcomes(max_age_hours=self._window_hours)
        if not pending:
            return

        evaluated = 0
        for entry in pending:
            try:
                outcome = self._evaluate_outcome(entry)
                if outcome is not None:
                    self._repo.update_outcome(
                        signal_id=entry["signal_id"],
                        exit_price=outcome["exit_price"],
                        outcome=outcome["outcome"],
                    )
                    evaluated += 1
            except Exception as exc:
                log.warning(
                    "Outcome evaluation failed for %s: %s",
                    entry["signal_id"],
                    exc,
                )

        if evaluated:
            log.info("OutcomeTracker: %d Signal(e) evaluiert", evaluated)

    def _evaluate_outcome(self, entry: dict) -> dict | None:
        """Evaluate a single signal outcome.

        Returns dict with exit_price and outcome (1=correct, 0=incorrect), or None on error.
        """
        pair = entry["pair"]
        action = entry["action"]
        entry_price = entry["entry_price"]

        try:
            current_price = self._get_price_fn(pair)
        except Exception as exc:
            log.warning("Price fetch failed for %s: %s", pair, exc)
            return None

        if current_price is None:
            return None

        if action == "BUY":
            outcome = 1 if current_price >= entry_price else 0
        elif action == "SELL":
            outcome = 1 if current_price <= entry_price else 0
        else:
            outcome = 0  # HOLD signals are never correct "trades"

        return {"exit_price": current_price, "outcome": outcome}

    @staticmethod
    def _default_get_price(pair: str) -> float | None:
        """Default price fetcher using core.market_data."""
        try:
            from core.market_data import MarketData

            md = MarketData()
            symbol = pair.replace("/", "")
            price = md.get_price(symbol)
            return price
        except Exception:
            return None
