import pytest
from unittest.mock import MagicMock

from core.signal_model import Signal
from trading.policies.base import Policy, PolicyResult, Severity
from trading.policies.symbol_whitelist import SymbolWhitelistPolicy
from trading.policies.max_position_size import MaxPositionSizePolicy
from trading.policies.max_drawdown import MaxDrawdownPolicy
from trading.policies.max_daily_loss import MaxDailyLossPolicy
from trading.policies.max_order_frequency import MaxOrderFrequencyPolicy
from trading.policies.manual_approval import ManualApprovalPolicy
from trading.safety_gateway import SafetyGateway


def _signal(**overrides):
    defaults = dict(
        pair="BTC/USDT",
        action="BUY",
        confidence=80,
        price=50000.0,
        quantity=0.1,
    )
    defaults.update(overrides)
    return Signal(**defaults)


# -- Helper Policies fuer Gateway-Tests --

class AlwaysPassPolicy(Policy):
    def check(self, signal, context):
        return PolicyResult(passed=True, severity=Severity.INFO, reason="ok", policy_name=self.name)


class AlwaysBlockPolicy(Policy):
    def check(self, signal, context):
        return PolicyResult(passed=False, severity=Severity.BLOCK, reason="blocked", policy_name=self.name)


class AlwaysPanicPolicy(Policy):
    def check(self, signal, context):
        return PolicyResult(passed=False, severity=Severity.PANIC, reason="panic!", policy_name=self.name)


class AlwaysWarnPolicy(Policy):
    def check(self, signal, context):
        return PolicyResult(passed=False, severity=Severity.WARN, reason="warning", policy_name=self.name)


# ============================================================
# Gateway Tests
# ============================================================


class TestSafetyGateway:
    def test_all_policies_pass(self):
        gw = SafetyGateway(policies=[AlwaysPassPolicy(), AlwaysPassPolicy()])
        result = gw.evaluate(_signal(), {})
        assert result.passed is True
        assert result.policy_name == "SafetyGateway"

    def test_one_policy_blocks(self):
        gw = SafetyGateway(policies=[AlwaysPassPolicy(), AlwaysBlockPolicy()])
        result = gw.evaluate(_signal(), {})
        assert result.passed is False
        assert result.severity == Severity.BLOCK

    def test_panic_stops_immediately(self):
        """PANIC short-circuits: zweite Policy wird nicht mehr ausgewertet."""
        panic = AlwaysPanicPolicy()
        block = AlwaysBlockPolicy()
        gw = SafetyGateway(policies=[panic, block])
        result = gw.evaluate(_signal(), {})
        assert result.passed is False
        assert result.severity == Severity.PANIC
        assert result.reason == "panic!"

    def test_no_policies(self):
        gw = SafetyGateway(policies=[])
        result = gw.evaluate(_signal(), {})
        assert result.passed is True
        assert result.policy_name == "SafetyGateway"

    def test_audit_logged(self):
        repo = MagicMock()
        gw = SafetyGateway(policies=[AlwaysPassPolicy(), AlwaysBlockPolicy()], repository=repo)
        gw.evaluate(_signal(), {})
        assert repo.log_audit.call_count == 2
        first_call = repo.log_audit.call_args_list[0]
        assert first_call[0][0] == "policy_AlwaysPassPolicy"
        second_call = repo.log_audit.call_args_list[1]
        assert second_call[0][0] == "policy_AlwaysBlockPolicy"

    def test_audit_not_called_without_repository(self):
        gw = SafetyGateway(policies=[AlwaysPassPolicy()])
        # Sollte ohne Fehler durchlaufen
        result = gw.evaluate(_signal(), {})
        assert result.passed is True

    def test_worst_severity_returned(self):
        """Mehrere fehlgeschlagene Policies → hoechste Severity zurueck."""
        gw = SafetyGateway(policies=[AlwaysWarnPolicy(), AlwaysBlockPolicy()])
        result = gw.evaluate(_signal(), {})
        assert result.passed is False
        assert result.severity == Severity.BLOCK

    def test_add_policy_dynamic(self):
        gw = SafetyGateway()
        assert gw.evaluate(_signal(), {}).passed is True
        gw.add_policy(AlwaysBlockPolicy())
        result = gw.evaluate(_signal(), {})
        assert result.passed is False

    def test_audit_details_structure(self):
        repo = MagicMock()
        gw = SafetyGateway(policies=[AlwaysBlockPolicy()], repository=repo)
        gw.evaluate(_signal(pair="ETH/USDT", action="SELL"), {})
        call_args = repo.log_audit.call_args
        event_type = call_args[0][0]
        details = call_args[0][1]
        assert event_type == "policy_AlwaysBlockPolicy"
        assert details["passed"] is False
        assert details["severity"] == "block"
        assert details["pair"] == "ETH/USDT"
        assert details["action"] == "SELL"


# ============================================================
# SymbolWhitelistPolicy Tests
# ============================================================


class TestSymbolWhitelistPolicy:
    def test_symbol_allowed(self):
        policy = SymbolWhitelistPolicy()
        result = policy.check(_signal(pair="BTC/USDT"), {})
        assert result.passed is True
        assert result.severity == Severity.INFO

    def test_symbol_blocked(self):
        policy = SymbolWhitelistPolicy()
        result = policy.check(_signal(pair="DOGE/USDT"), {})
        assert result.passed is False
        assert result.severity == Severity.BLOCK
        assert "DOGE/USDT" in result.reason

    def test_symbol_without_slash(self):
        policy = SymbolWhitelistPolicy()
        result = policy.check(_signal(pair="BTCUSDT"), {})
        assert result.passed is True


# ============================================================
# MaxPositionSizePolicy Tests
# ============================================================


class TestMaxPositionSizePolicy:
    def test_position_size_passes(self):
        policy = MaxPositionSizePolicy()
        # price=50000 * quantity=0.1 = 5000, capital=100000 * 0.10 = 10000
        result = policy.check(_signal(price=50000.0, quantity=0.1), {"starting_capital": 100000.0})
        assert result.passed is True

    def test_position_size_blocks(self):
        policy = MaxPositionSizePolicy()
        # price=50000 * quantity=0.5 = 25000, capital=100000 * 0.10 = 10000
        result = policy.check(_signal(price=50000.0, quantity=0.5), {"starting_capital": 100000.0})
        assert result.passed is False
        assert result.severity == Severity.BLOCK

    def test_position_size_exact_limit(self):
        policy = MaxPositionSizePolicy()
        # price=10000 * quantity=1.0 = 10000, capital=100000 * 0.10 = 10000
        result = policy.check(_signal(price=10000.0, quantity=1.0), {"starting_capital": 100000.0})
        assert result.passed is True

    def test_position_size_zero_capital(self):
        policy = MaxPositionSizePolicy()
        result = policy.check(_signal(price=100.0, quantity=1.0), {"starting_capital": 0.0})
        assert result.passed is False


# ============================================================
# MaxDrawdownPolicy Tests
# ============================================================


class TestMaxDrawdownPolicy:
    def test_drawdown_within_limits(self):
        policy = MaxDrawdownPolicy()
        result = policy.check(_signal(), {"current_drawdown_pct": 0.10})
        assert result.passed is True

    def test_drawdown_exceeds_triggers_panic(self):
        policy = MaxDrawdownPolicy()
        result = policy.check(_signal(), {"current_drawdown_pct": 0.25})
        assert result.passed is False
        assert result.severity == Severity.PANIC

    def test_drawdown_at_exact_limit(self):
        policy = MaxDrawdownPolicy()
        # MAX_DRAWDOWN_PCT default = 0.20
        result = policy.check(_signal(), {"current_drawdown_pct": 0.20})
        assert result.passed is True


# ============================================================
# MaxDailyLossPolicy Tests
# ============================================================


class TestMaxDailyLossPolicy:
    def test_daily_loss_within_limits(self):
        policy = MaxDailyLossPolicy()
        result = policy.check(_signal(), {"daily_loss_pct": 0.05})
        assert result.passed is True

    def test_daily_loss_exceeds_triggers_panic(self):
        policy = MaxDailyLossPolicy()
        result = policy.check(_signal(), {"daily_loss_pct": 0.15})
        assert result.passed is False
        assert result.severity == Severity.PANIC

    def test_daily_loss_custom_threshold(self):
        policy = MaxDailyLossPolicy(max_daily_loss_pct=0.05)
        result = policy.check(_signal(), {"daily_loss_pct": 0.08})
        assert result.passed is False
        assert result.severity == Severity.PANIC


# ============================================================
# MaxOrderFrequencyPolicy Tests
# ============================================================


class TestMaxOrderFrequencyPolicy:
    def test_frequency_within_limits(self):
        policy = MaxOrderFrequencyPolicy()
        result = policy.check(_signal(), {"recent_order_count": 5})
        assert result.passed is True

    def test_frequency_exceeds_blocks(self):
        policy = MaxOrderFrequencyPolicy()
        result = policy.check(_signal(), {"recent_order_count": 12})
        assert result.passed is False
        assert result.severity == Severity.BLOCK

    def test_frequency_custom_limit(self):
        policy = MaxOrderFrequencyPolicy(max_orders_per_hour=5)
        result = policy.check(_signal(), {"recent_order_count": 5})
        assert result.passed is False

    def test_frequency_at_limit_passes(self):
        policy = MaxOrderFrequencyPolicy(max_orders_per_hour=10)
        result = policy.check(_signal(), {"recent_order_count": 9})
        assert result.passed is True


# ============================================================
# ManualApprovalPolicy Tests
# ============================================================


class TestManualApprovalPolicy:
    def test_dry_run_passes(self):
        policy = ManualApprovalPolicy()
        result = policy.check(_signal(mode="dry_run"), {})
        assert result.passed is True
        assert "Dry-run" in result.reason

    def test_non_dry_run_without_approval_blocks(self):
        # Signal erzwingt dry_run via __post_init__, daher muessen wir
        # den mode manuell pruefen. Da Signal frozen ist, muessen wir
        # den Context nutzen.
        policy = ManualApprovalPolicy()
        # Signal.mode wird immer "dry_run" via __post_init__, daher testen wir
        # ueber den approved-context
        signal = _signal()
        # Da __post_init__ mode auf dry_run setzt, muessen wir
        # das Signal mit object.__setattr__ manipulieren
        object.__setattr__(signal, "mode", "live")
        result = policy.check(signal, {"approved": False})
        assert result.passed is False
        assert result.severity == Severity.BLOCK

    def test_non_dry_run_with_approval_passes(self):
        policy = ManualApprovalPolicy()
        signal = _signal()
        object.__setattr__(signal, "mode", "live")
        result = policy.check(signal, {"approved": True})
        assert result.passed is True


# ============================================================
# Severity Ordering Tests
# ============================================================


class TestSeverityOrdering:
    def test_info_lt_warn(self):
        assert Severity.INFO < Severity.WARN

    def test_warn_lt_block(self):
        assert Severity.WARN < Severity.BLOCK

    def test_block_lt_panic(self):
        assert Severity.BLOCK < Severity.PANIC

    def test_panic_gt_all(self):
        assert Severity.PANIC > Severity.BLOCK
        assert Severity.PANIC > Severity.WARN
        assert Severity.PANIC > Severity.INFO
