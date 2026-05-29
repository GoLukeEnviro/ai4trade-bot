import config
from trading.policies.base import Policy, PolicyResult, Severity


class MaxDrawdownPolicy(Policy):
    def check(self, signal, context: dict) -> PolicyResult:
        current_drawdown_pct = context.get("current_drawdown_pct", 0.0)
        max_dd = config.MAX_DRAWDOWN_PCT

        if current_drawdown_pct <= max_dd:
            return PolicyResult(
                passed=True,
                severity=Severity.INFO,
                reason="Drawdown within limits",
                policy_name=self.name,
            )
        return PolicyResult(
            passed=False,
            severity=Severity.PANIC,
            reason=f"Drawdown {current_drawdown_pct * 100:.1f}% exceeds {max_dd * 100:.0f}% hard stop",
            policy_name=self.name,
        )
