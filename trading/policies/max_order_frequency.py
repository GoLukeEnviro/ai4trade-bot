from trading.policies.base import Policy, PolicyResult, Severity


class MaxOrderFrequencyPolicy(Policy):
    def __init__(self, max_orders_per_hour: int = 10):
        self._max_orders_per_hour = max_orders_per_hour

    def check(self, signal, context: dict) -> PolicyResult:
        recent_order_count = context.get("recent_order_count", 0)

        if recent_order_count < self._max_orders_per_hour:
            return PolicyResult(
                passed=True,
                severity=Severity.INFO,
                reason="Order frequency within limits",
                policy_name=self.name,
            )
        return PolicyResult(
            passed=False,
            severity=Severity.BLOCK,
            reason=f"Order frequency {recent_order_count} exceeds {self._max_orders_per_hour}/hour",
            policy_name=self.name,
        )
