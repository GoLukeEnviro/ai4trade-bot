from __future__ import annotations

from core.signal_model import Signal
from trading.policies.base import Policy, PolicyResult, Severity


class SafetyGateway:
    def __init__(self, policies: list[Policy] | None = None, repository=None):
        self._policies: list[Policy] = policies or []
        self._repository = repository

    def add_policy(self, policy: Policy) -> None:
        self._policies.append(policy)

    def evaluate(self, signal: Signal, context: dict) -> PolicyResult:
        """
        Evaluate all policies. Fail-closed: any BLOCK/PANIC = rejected.
        Returns worst-case result (highest severity that failed).
        PANIC causes immediate short-circuit.
        """
        worst_result: PolicyResult | None = None
        for policy in self._policies:
            result = policy.check(signal, context)
            self._audit(result, signal)
            if not result.passed:
                if worst_result is None or result.severity > worst_result.severity:
                    worst_result = result
                if result.severity == Severity.PANIC:
                    return result
        if worst_result:
            return worst_result
        return PolicyResult(
            passed=True,
            severity=Severity.INFO,
            reason="All policies passed",
            policy_name="SafetyGateway",
        )

    def _audit(self, result: PolicyResult, signal: Signal) -> None:
        if self._repository is not None:
            self._repository.log_audit(
                f"policy_{result.policy_name}",
                {
                    "passed": result.passed,
                    "severity": result.severity.value,
                    "reason": result.reason,
                    "pair": signal.pair,
                    "action": signal.action,
                },
            )
