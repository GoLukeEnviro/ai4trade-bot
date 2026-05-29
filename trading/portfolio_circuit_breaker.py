from __future__ import annotations

import logging
import time

from core.signal_model import Signal

log = logging.getLogger(__name__)


class PortfolioCircuitBreaker:
    """
    Portfolio-level circuit breaker. HARD STOP bei Anomalien.
    State persistent in app_state-Tabelle.
    Nach Ausloesung: Nur HOLD-Signale, manuelle Reaktivierung noetig.
    """

    DEFAULTS = {
        "max_consecutive_losses": 5,
        "max_daily_loss_pct": 0.10,
        "max_api_latency_seconds": 10.0,
        "max_slippage_pct": 0.02,
        "max_rejected_rate_pct": 0.10,
        "max_atr_multiplier": 3.0,
    }

    def __init__(self, repository=None, config: dict | None = None):
        self._repository = repository
        self._config = {**self.DEFAULTS, **(config or {})}
        self._consecutive_losses = 0
        self._daily_pnl = 0.0
        self._daily_reset = time.time()
        self._api_latencies: list[float] = []
        self._rejected_count = 0
        self._total_requests = 0
        self._rejected_window_start = time.time()
        self._activated_at: float | None = None

        self._load_state()

    def is_active(self) -> bool:
        """Circuit Breaker aktiv?"""
        return self._activated_at is not None

    def check_signal(self, signal: Signal) -> tuple[bool, str]:
        """
        Pruefe ob Signal durchgelassen wird.
        Returns (allowed, reason).
        Wenn aktiv: Nur HOLD erlaubt.
        """
        if not self.is_active():
            return True, "circuit_breaker inactive"

        if signal.action == "HOLD":
            return True, "circuit_breaker active, HOLD allowed"
        return False, f"circuit_breaker ACTIVE since {self._activated_at}"

    def record_trade_result(self, pnl: float) -> None:
        """Trade-Ergebnis erfassen (fuer consecutive loss tracking)."""
        self._reset_daily_if_needed()
        self._daily_pnl += pnl

        if pnl < 0:
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0

        self._check_conditions()

    def record_api_latency(self, latency_seconds: float) -> None:
        """API-Latenz erfassen."""
        self._api_latencies.append(latency_seconds)
        if len(self._api_latencies) > 100:
            self._api_latencies = self._api_latencies[-100:]
        self._check_conditions()

    def record_request_result(self, rejected: bool) -> None:
        """Exchange-Request Ergebnis erfassen."""
        self._reset_rejected_window_if_needed()
        self._total_requests += 1
        if rejected:
            self._rejected_count += 1
        self._check_conditions()

    def activate(self, reason: str) -> None:
        """Manuell oder automatisch aktivieren."""
        if self.is_active():
            return
        self._activated_at = time.time()
        log.error("CIRCUIT BREAKER ACTIVATED: %s", reason)
        self._save_state()
        self._audit("circuit_breaker_activated", {"reason": reason})
        try:
            from core.metrics import CIRCUIT_BREAKER_ACTIVE

            CIRCUIT_BREAKER_ACTIVE.set(1)
        except ImportError:
            pass

    def deactivate(self) -> None:
        """Manuelle Reaktivierung."""
        self._activated_at = None
        self._consecutive_losses = 0
        self._daily_pnl = 0.0
        self._api_latencies.clear()
        self._rejected_count = 0
        self._total_requests = 0
        log.info("Circuit Breaker DEACTIVATED (manual)")
        self._save_state()
        self._audit("circuit_breaker_deactivated", {})
        try:
            from core.metrics import CIRCUIT_BREAKER_ACTIVE

            CIRCUIT_BREAKER_ACTIVE.set(0)
        except ImportError:
            pass

    # -- Private ----------------------------------------------------------

    def _check_conditions(self) -> None:
        """Alle Bedingungen pruefen, ggf. aktivieren."""
        if self.is_active():
            return

        if self._consecutive_losses >= self._config["max_consecutive_losses"]:
            self.activate(f"{self._consecutive_losses} consecutive losing trades")
            return

        max_daily = self._config["max_daily_loss_pct"]
        if self._daily_pnl < 0 and abs(self._daily_pnl) > max_daily:
            self.activate(
                f"daily loss {abs(self._daily_pnl):.2%} exceeds {max_daily:.0%}"
            )
            return

        if len(self._api_latencies) >= 10:
            p99 = sorted(self._api_latencies)[int(len(self._api_latencies) * 0.99)]
            if p99 > self._config["max_api_latency_seconds"]:
                self.activate(
                    f"API latency P99={p99:.1f}s exceeds "
                    f"{self._config['max_api_latency_seconds']}s"
                )
                return

        if self._total_requests >= 10:
            rate = self._rejected_count / self._total_requests
            if rate > self._config["max_rejected_rate_pct"]:
                self.activate(
                    f"rejected rate {rate:.1%} exceeds "
                    f"{self._config['max_rejected_rate_pct']:.0%}"
                )
                return

    def _reset_daily_if_needed(self) -> None:
        now = time.time()
        if now - self._daily_reset >= 86400:
            self._daily_pnl = 0.0
            self._daily_reset = now

    def _reset_rejected_window_if_needed(self) -> None:
        now = time.time()
        if now - self._rejected_window_start >= 300:
            self._rejected_count = 0
            self._total_requests = 0
            self._rejected_window_start = now

    def _load_state(self) -> None:
        if self._repository is None:
            return
        state = self._repository.get_state("circuit_breaker_active")
        if state == "1":
            self._activated_at = float(
                self._repository.get_state("circuit_breaker_activated_at", "0")
            )

    def _save_state(self) -> None:
        if self._repository is None:
            return
        self._repository.set_state(
            "circuit_breaker_active", "1" if self.is_active() else "0"
        )
        if self._activated_at is not None:
            self._repository.set_state(
                "circuit_breaker_activated_at", str(self._activated_at)
            )

    def _audit(self, event_type: str, details: dict) -> None:
        if self._repository is not None:
            self._repository.log_audit(event_type, details)
