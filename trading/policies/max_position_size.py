import config
from trading.policies.base import Policy, PolicyResult, Severity


class MaxPositionSizePolicy(Policy):
    def check(self, signal, context: dict) -> PolicyResult:
        starting_capital = context.get("starting_capital", 0.0)
        max_pct = config.MAX_POSITION_PCT
        trade_value = signal.price * signal.quantity
        limit = starting_capital * max_pct

        if trade_value <= limit:
            return PolicyResult(
                passed=True,
                severity=Severity.INFO,
                reason="Position size within limits",
                policy_name=self.name,
            )
        return PolicyResult(
            passed=False,
            severity=Severity.BLOCK,
            reason=f"Position size {trade_value:.2f} exceeds {max_pct * 100:.0f}% limit ({limit:.2f})",
            policy_name=self.name,
        )
