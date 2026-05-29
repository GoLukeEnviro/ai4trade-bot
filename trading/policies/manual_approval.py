from trading.policies.base import Policy, PolicyResult, Severity


class ManualApprovalPolicy(Policy):
    def check(self, signal, context: dict) -> PolicyResult:
        if signal.mode == "dry_run":
            return PolicyResult(
                passed=True,
                severity=Severity.INFO,
                reason="Dry-run mode, approval not required",
                policy_name=self.name,
            )

        approved = context.get("approved", False)
        if approved:
            return PolicyResult(
                passed=True,
                severity=Severity.INFO,
                reason="Manual approval granted",
                policy_name=self.name,
            )
        return PolicyResult(
            passed=False,
            severity=Severity.BLOCK,
            reason="Manual approval required for non-dry-run mode",
            policy_name=self.name,
        )
