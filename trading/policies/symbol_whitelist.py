from trading.policies.base import Policy, PolicyResult, Severity
import config


class SymbolWhitelistPolicy(Policy):
    def check(self, signal, context: dict) -> PolicyResult:
        allowed = [p.replace("/", "") for p in config.TRADING_PAIRS]
        symbol = signal.pair.replace("/", "")
        if symbol in allowed:
            return PolicyResult(
                passed=True,
                severity=Severity.INFO,
                reason="Symbol allowed",
                policy_name=self.name,
            )
        return PolicyResult(
            passed=False,
            severity=Severity.BLOCK,
            reason=f"Symbol {signal.pair} not in whitelist",
            policy_name=self.name,
        )
