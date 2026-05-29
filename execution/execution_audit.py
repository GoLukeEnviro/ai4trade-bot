from __future__ import annotations

from execution.execution_models import OrderResult


def log_execution(result: OrderResult, repository=None) -> None:
    """
    Jede Order (versucht, ausgefuehrt, abgelehnt) wird persistiert.
    """
    if repository is None:
        return
    repository.log_audit("execution_result", {
        "pair": result.request.pair,
        "action": result.request.action,
        "status": result.status.value,
        "reason": result.reason,
        "filled_price": result.filled_price,
        "filled_quantity": result.filled_quantity,
    })
