from __future__ import annotations

import logging

from core.signal_model import Signal
from execution.execution_models import OrderRequest, OrderResult, ExecutionStatus
from trading.portfolio_circuit_breaker import PortfolioCircuitBreaker
from trading.safety_gateway import SafetyGateway

log = logging.getLogger(__name__)


class OrderExecutor:
    """
    Nimmt validiertes Signal -> prueft Safety + Circuit Breaker -> erstellt Order -> sendet an Exchange.
    Dry-Run: Signal-Publishing. Spater: echte Exchange-Order durch Austausch des Executors.
    """

    def __init__(
        self,
        publisher=None,
        safety_gateway: SafetyGateway | None = None,
        circuit_breaker: PortfolioCircuitBreaker | None = None,
        repository=None,
    ):
        self._publisher = publisher
        self._safety = safety_gateway
        self._circuit_breaker = circuit_breaker
        self._repository = repository

    def execute(self, signal: Signal, context: dict | None = None) -> OrderResult:
        """
        Signal ausfuehren. Flow:
        1. Circuit Breaker Check
        2. Safety Gateway Check
        3. HOLD -> SKIP
        4. Publisher -> SUBMITTED (dry-run) oder FILLED
        5. Fehler -> FAILED
        """
        context = context or {}
        request = self._signal_to_request(signal)

        # 1. Circuit Breaker
        if self._circuit_breaker is not None:
            allowed, reason = self._circuit_breaker.check_signal(signal)
            if not allowed:
                self._audit("execution_circuit_breaker_block", signal, reason)
                return OrderResult(request=request, status=ExecutionStatus.REJECTED, reason=reason)

        # 2. Safety Gateway
        if self._safety is not None:
            result = self._safety.evaluate(signal, context)
            if not result.passed:
                self._audit("execution_safety_block", signal, result.reason)
                return OrderResult(request=request, status=ExecutionStatus.REJECTED, reason=result.reason)

        # 3. HOLD -> SKIP
        if signal.action == "HOLD":
            return OrderResult(request=request, status=ExecutionStatus.SKIPPED, reason="HOLD signal")

        # 4. Publish
        if self._publisher is not None:
            try:
                success = self._publisher.publish(signal)
                if success:
                    self._audit("execution_submitted", signal, "dry_run_publish_ok")
                    return OrderResult(
                        request=request,
                        status=ExecutionStatus.SUBMITTED,
                        reason="dry_run_mode",
                    )
                else:
                    self._audit("execution_publish_failed", signal, "publish_returned_false")
                    return OrderResult(request=request, status=ExecutionStatus.FAILED, reason="publish failed")
            except Exception as e:
                self._audit("execution_publish_error", signal, str(e))
                return OrderResult(request=request, status=ExecutionStatus.FAILED, reason=str(e))

        # 5. No publisher -> log only
        self._audit("execution_no_publisher", signal, "no_publisher_configured")
        return OrderResult(request=request, status=ExecutionStatus.SKIPPED, reason="no publisher")

    def _signal_to_request(self, signal: Signal) -> OrderRequest:
        return OrderRequest(
            pair=signal.pair,
            action=signal.action,
            price=signal.price,
            quantity=signal.quantity,
            signal_confidence=signal.confidence,
            mode=signal.mode,
        )

    def _audit(self, event_type: str, signal: Signal, reason: str) -> None:
        log.info("Execution %s: %s %s - %s", event_type, signal.pair, signal.action, reason)
        if self._repository is not None:
            self._repository.log_audit(event_type, {
                "pair": signal.pair,
                "action": signal.action,
                "confidence": signal.confidence,
                "reason": reason,
            })
