from trading.policies.base import Policy, PolicyResult, Severity


class MaxDailyLossPolicy(Policy):
    def __init__(self, max_daily_loss_pct: float = 0.10):
        self._max_daily_loss_pct = max_daily_loss_pct

    def check(self, signal, context: dict) -> PolicyResult:
        daily_loss_pct = context.get("daily_loss_pct", 0.0)

        if daily_loss_pct <= self._max_daily_loss_pct:
            return PolicyResult(
                passed=True,
                severity=Severity.INFO,
                reason="Daily loss within limits",
                policy_name=self.name,
            )
        return PolicyResult(
            passed=False,
            severity=Severity.PANIC,
            reason=f"Daily loss {daily_loss_pct * 100:.1f}% exceeds {self._max_daily_loss_pct * 100:.0f}% threshold",
            policy_name=self.name,
        )
