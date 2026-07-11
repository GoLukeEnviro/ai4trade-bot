"""Tests for notification rule checker (Issue #19)."""

from __future__ import annotations

import time
from unittest.mock import patch

from core.signals.envelope import (
    CanonicalSignalEnvelope,
    DataQuality,
    DataQualityStatus,
    SignalClass,
    SignalDirection,
    SignalPriority,
)
from core.signals.notification_rules import NotificationRuleChecker


def _envelope(
    signal_class: SignalClass = SignalClass.ENTRY,
    priority: SignalPriority = SignalPriority.MEDIUM,
    confidence: float = 0.5,
    risk_score: float = 0.5,
    asset: str = "BTC/USDT",
) -> CanonicalSignalEnvelope:
    return CanonicalSignalEnvelope(
        signal_class=signal_class,
        subtype="test",
        source="test",
        asset=asset,
        direction=SignalDirection.BULLISH,
        confidence=confidence,
        risk_score=risk_score,
        priority=priority,
        data_quality=DataQuality(status=DataQualityStatus.OK),
        actionability={"can_alert": True},
        invalidation={"max_age_seconds": 3600, "conditions": []},
        raw_refs=[],
    )


class TestNotificationRules:
    """Test all 4 rules + cooldown."""

    def setup_method(self) -> None:
        self.checker = NotificationRuleChecker(cooldown_seconds=300)

    # ---- Rule 1: critical priority always notifies ----

    def test_rule1_critical_priority_notifies(self) -> None:
        env = _envelope(priority=SignalPriority.CRITICAL)
        ok, reason = self.checker.should_notify(env)
        assert ok is True
        assert reason == "critical_priority"

    def test_first_notification_is_not_treated_as_a_cooldown(self) -> None:
        env = _envelope(priority=SignalPriority.CRITICAL)

        with patch("core.signals.notification_rules.time.monotonic", return_value=1.0):
            ok, reason = self.checker.should_notify(env)

        assert ok is True
        assert reason == "critical_priority"

    def test_rule1_critical_on_any_class(self) -> None:
        for sc in SignalClass:
            env = _envelope(signal_class=sc, priority=SignalPriority.CRITICAL)
            ok, _ = self.checker.should_notify(env)
            assert ok is True, f"Expected notify for {sc}"

    # ---- Rule 2: meta class + high/critical ----

    def test_rule2_risk_high_notifies(self) -> None:
        env = _envelope(
            signal_class=SignalClass.RISK,
            priority=SignalPriority.HIGH,
        )
        ok, reason = self.checker.should_notify(env)
        assert ok is True
        assert reason == "meta_high_priority"

    def test_rule2_system_health_critical_notifies(self) -> None:
        env = _envelope(
            signal_class=SignalClass.SYSTEM_HEALTH,
            priority=SignalPriority.CRITICAL,
        )
        ok, reason = self.checker.should_notify(env)
        assert ok is True
        assert reason == "critical_priority"  # rule 1 fires first

    def test_rule2_data_quality_high_notifies(self) -> None:
        env = _envelope(
            signal_class=SignalClass.DATA_QUALITY,
            priority=SignalPriority.HIGH,
        )
        ok, reason = self.checker.should_notify(env)
        assert ok is True
        assert reason == "meta_high_priority"

    def test_rule2_meta_class_medium_does_not_notify(self) -> None:
        env = _envelope(
            signal_class=SignalClass.RISK,
            priority=SignalPriority.MEDIUM,
        )
        ok, reason = self.checker.should_notify(env)
        assert ok is False
        assert reason == "no_rule_matched"

    # ---- Rule 3: ENTRY + high confidence + low risk ----

    def test_rule3_entry_high_conf_low_risk_notifies(self) -> None:
        env = _envelope(
            signal_class=SignalClass.ENTRY,
            confidence=0.75,
            risk_score=0.4,
        )
        ok, reason = self.checker.should_notify(env)
        assert ok is True
        assert reason == "high_confidence_low_risk_entry"

    def test_rule3_entry_low_conf_does_not_notify(self) -> None:
        env = _envelope(
            signal_class=SignalClass.ENTRY,
            confidence=0.5,
            risk_score=0.4,
        )
        ok, _ = self.checker.should_notify(env)
        assert ok is False

    def test_rule3_entry_high_risk_does_not_notify(self) -> None:
        env = _envelope(
            signal_class=SignalClass.ENTRY,
            confidence=0.8,
            risk_score=0.7,
        )
        ok, _ = self.checker.should_notify(env)
        assert ok is False

    def test_rule3_entry_boundary_confidence_0_7(self) -> None:
        env = _envelope(confidence=0.7, risk_score=0.5)
        ok, _ = self.checker.should_notify(env)
        assert ok is True

    def test_rule3_entry_boundary_risk_0_6(self) -> None:
        env = _envelope(confidence=0.8, risk_score=0.6)
        ok, _ = self.checker.should_notify(env)
        assert ok is False  # risk_score < 0.6 is required, 0.6 fails

    # ---- Rule 4: everything else ----

    def test_rule4_exit_medium_not_notified(self) -> None:
        env = _envelope(signal_class=SignalClass.EXIT)
        ok, reason = self.checker.should_notify(env)
        assert ok is False
        assert reason == "no_rule_matched"

    def test_rule4_regime_medium_not_notified(self) -> None:
        env = _envelope(signal_class=SignalClass.REGIME)
        ok, _ = self.checker.should_notify(env)
        assert ok is False

    # ---- Cooldown ----

    def test_cooldown_blocks_repeat(self) -> None:
        env = _envelope(
            signal_class=SignalClass.RISK,
            priority=SignalPriority.HIGH,
        )
        ok1, _ = self.checker.should_notify(env)
        assert ok1 is True

        # Second call within cooldown window
        ok2, reason2 = self.checker.should_notify(env)
        assert ok2 is False
        assert "cooldown_active" in reason2

    def test_cooldown_allows_after_expiry(self) -> None:
        checker = NotificationRuleChecker(cooldown_seconds=1.0)
        env = _envelope(priority=SignalPriority.CRITICAL)
        ok1, _ = checker.should_notify(env)
        assert ok1 is True

        # Simulate cooldown expiry
        key = (env.asset, env.signal_class.value)
        checker._last_notification[key] = time.monotonic() - 2.0

        ok2, _ = checker.should_notify(env)
        assert ok2 is True

    def test_cooldown_per_asset_class_pair(self) -> None:
        env_btc = _envelope(
            asset="BTC/USDT",
            signal_class=SignalClass.RISK,
            priority=SignalPriority.HIGH,
        )
        env_eth = _envelope(
            asset="ETH/USDT",
            signal_class=SignalClass.RISK,
            priority=SignalPriority.HIGH,
        )
        ok1, _ = self.checker.should_notify(env_btc)
        assert ok1 is True

        # Different asset — should still notify
        ok2, _ = self.checker.should_notify(env_eth)
        assert ok2 is True
