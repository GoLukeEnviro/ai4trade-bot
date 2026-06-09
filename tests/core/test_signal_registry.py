"""Tests for Issue #14 — Canonical Signal Registry and Lifecycle Events."""

from __future__ import annotations

import pytest

from core.signals.envelope import (
    Actionability,
    CanonicalSignalEnvelope,
    DataQuality,
    DataQualityStatus,
    SignalClass,
    SignalDirection,
    SignalPriority,
)
from core.signals.registry import CanonicalSignalRegistry, SignalLifecycle

# ======================================================================
# Helpers
# ======================================================================

def _make_envelope(**overrides) -> CanonicalSignalEnvelope:
    defaults = dict(
        signal_class=SignalClass.ENTRY,
        subtype="test",
        source="unit-test",
        asset="BTC/USDT",
        direction=SignalDirection.BULLISH,
        confidence=0.75,
        risk_score=0.3,
        priority=SignalPriority.MEDIUM,
        reason_codes=["test"],
        features={},
        data_quality=DataQuality(status=DataQualityStatus.OK),
        actionability=Actionability(can_alert=True),
        raw_refs=[],
    )
    defaults.update(overrides)
    return CanonicalSignalEnvelope(**defaults)


@pytest.fixture()
def registry(tmp_path):
    """Provide a registry backed by a temp database."""
    db = tmp_path / "test_signals.db"
    reg = CanonicalSignalRegistry(db_path=str(db))
    yield reg
    reg.close()


# ======================================================================
# Append and query
# ======================================================================

class TestAppendAndQuery:
    def test_append_returns_id(self, registry):
        env = _make_envelope()
        sid = registry.append(env)
        assert sid == env.id

    def test_get_signal(self, registry):
        env = _make_envelope()
        registry.append(env)
        result = registry.get_signal(env.id)
        assert result is not None
        assert result["id"] == env.id
        assert result["asset"] == "BTC/USDT"

    def test_get_signal_not_found(self, registry):
        assert registry.get_signal("nonexistent") is None

    def test_query_latest_returns_in_order(self, registry):
        env1 = _make_envelope(asset="AAA/USDT")
        env2 = _make_envelope(asset="BBB/USDT")
        registry.append(env1)
        registry.append(env2)
        results = registry.query_latest(limit=10)
        assert len(results) == 2
        # most recent first
        assert results[0]["asset"] == "BBB/USDT"
        assert results[1]["asset"] == "AAA/USDT"

    def test_query_latest_respects_limit(self, registry):
        for i in range(5):
            registry.append(_make_envelope(asset=f"COIN{i}/USDT"))
        results = registry.query_latest(limit=2)
        assert len(results) == 2


# ======================================================================
# Lifecycle transitions
# ======================================================================

class TestLifecycleTransitions:
    def test_initial_lifecycle_is_emitted(self, registry):
        env = _make_envelope()
        registry.append(env)
        result = registry.get_signal(env.id)
        assert result["lifecycle"] == "emitted"

    def test_transition_to_resolved_win(self, registry):
        env = _make_envelope()
        registry.append(env)
        ok = registry.transition(env.id, SignalLifecycle.RESOLVED_WIN, reason="tp_hit")
        assert ok is True
        result = registry.get_signal(env.id)
        assert result["lifecycle"] == "resolved_win"
        assert result["transition_reason"] == "tp_hit"

    def test_transition_to_resolved_loss(self, registry):
        env = _make_envelope()
        registry.append(env)
        registry.transition(env.id, SignalLifecycle.RESOLVED_LOSS, reason="sl_hit")
        result = registry.get_signal(env.id)
        assert result["lifecycle"] == "resolved_loss"

    def test_transition_to_expired(self, registry):
        env = _make_envelope()
        registry.append(env)
        registry.transition(env.id, SignalLifecycle.EXPIRED)
        result = registry.get_signal(env.id)
        assert result["lifecycle"] == "expired"

    def test_transition_to_invalidated(self, registry):
        env = _make_envelope()
        registry.append(env)
        registry.transition(env.id, SignalLifecycle.INVALIDATED, reason="regime_change")
        result = registry.get_signal(env.id)
        assert result["lifecycle"] == "invalidated"

    def test_transition_nonexistent_returns_false(self, registry):
        ok = registry.transition("nonexistent", SignalLifecycle.EXPIRED)
        assert ok is False

    def test_multiple_transitions(self, registry):
        env = _make_envelope()
        registry.append(env)
        registry.transition(env.id, SignalLifecycle.EMITTED)
        registry.transition(env.id, SignalLifecycle.EXPIRED, reason="time")
        result = registry.get_signal(env.id)
        assert result["lifecycle"] == "expired"
        assert result["transition_reason"] == "time"


# ======================================================================
# Query by asset and class
# ======================================================================

class TestQueryFilters:
    def test_query_by_asset(self, registry):
        registry.append(_make_envelope(asset="BTC/USDT"))
        registry.append(_make_envelope(asset="ETH/USDT"))
        results = registry.query_latest(asset="BTC/USDT")
        assert len(results) == 1
        assert results[0]["asset"] == "BTC/USDT"

    def test_query_by_class(self, registry):
        registry.append(_make_envelope(signal_class=SignalClass.ENTRY))
        registry.append(_make_envelope(signal_class=SignalClass.EXIT, asset="ETH/USDT"))
        results = registry.query_latest(signal_class=SignalClass.EXIT)
        assert len(results) == 1
        assert results[0]["signal_class"] == "exit"

    def test_query_by_asset_and_class(self, registry):
        registry.append(_make_envelope(asset="BTC/USDT", signal_class=SignalClass.ENTRY))
        registry.append(_make_envelope(asset="BTC/USDT", signal_class=SignalClass.EXIT))
        registry.append(_make_envelope(asset="ETH/USDT", signal_class=SignalClass.ENTRY))
        results = registry.query_latest(asset="BTC/USDT", signal_class=SignalClass.ENTRY)
        assert len(results) == 1


# ======================================================================
# Active signals filter
# ======================================================================

class TestActiveSignals:
    def test_active_excludes_expired(self, registry):
        env1 = _make_envelope(asset="AAA/USDT")
        registry.append(env1)
        registry.transition(env1.id, SignalLifecycle.EXPIRED)
        env2 = _make_envelope(asset="BBB/USDT")
        registry.append(env2)
        active = registry.query_active()
        assert len(active) == 1
        assert active[0]["asset"] == "BBB/USDT"

    def test_active_excludes_invalidated(self, registry):
        env = _make_envelope()
        registry.append(env)
        registry.transition(env.id, SignalLifecycle.INVALIDATED)
        assert registry.query_active() == []

    def test_active_includes_resolved_win(self, registry):
        env = _make_envelope()
        registry.append(env)
        registry.transition(env.id, SignalLifecycle.RESOLVED_WIN)
        active = registry.query_active()
        assert len(active) == 1

    def test_active_filter_by_asset(self, registry):
        env1 = _make_envelope(asset="BTC/USDT")
        registry.append(env1)
        env2 = _make_envelope(asset="ETH/USDT")
        registry.append(env2)
        registry.transition(env2.id, SignalLifecycle.EXPIRED)
        active = registry.query_active(asset="BTC/USDT")
        assert len(active) == 1
        assert active[0]["asset"] == "BTC/USDT"

    def test_active_empty_when_all_expired(self, registry):
        for i in range(3):
            env = _make_envelope(asset=f"COIN{i}/USDT")
            registry.append(env)
            registry.transition(env.id, SignalLifecycle.EXPIRED)
        assert registry.query_active() == []


# ======================================================================
# Cleanup and vacuum
# ======================================================================

class TestCleanupExpired:
    def test_cleanup_expired_deletes_old(self, registry):
        """Insert a signal with a past created_at, then clean it up."""
        from datetime import UTC, datetime, timedelta

        env = _make_envelope()
        # Manually insert with an old created_at
        old_time = datetime.now(UTC) - timedelta(hours=48)
        import json
        payload = env.model_dump(mode="json")
        payload["signal_class"] = payload.pop("class", payload.get("signal_class"))
        envelope_json = json.dumps(payload, default=str)
        with registry._lock:
            registry._conn.execute(
                "INSERT INTO canonical_signals "
                "(id, envelope_json, lifecycle, created_at, asset, signal_class, updated_at) "
                "VALUES (?, ?, 'emitted', ?, ?, ?, ?)",
                (env.id, envelope_json, str(old_time), env.asset, env.signal_class.value, str(old_time)),
            )
            registry._conn.commit()
        deleted = registry.cleanup_expired(max_age_hours=24)
        assert deleted == 1
        assert registry.get_signal(env.id) is None

    def test_cleanup_expired_keeps_recent(self, registry):
        """Signals newer than the cutoff are NOT deleted."""
        env = _make_envelope()
        registry.append(env)
        deleted = registry.cleanup_expired(max_age_hours=24)
        assert deleted == 0
        assert registry.get_signal(env.id) is not None

    def test_cleanup_expired_empty_db(self, registry):
        """Cleanup on an empty DB returns 0."""
        deleted = registry.cleanup_expired(max_age_hours=24)
        assert deleted == 0


class TestVacuum:
    def test_vacuum_does_not_crash(self, registry):
        """VACUUM should run without error on a populated DB."""
        for i in range(5):
            registry.append(_make_envelope(asset=f"COIN{i}/USDT"))
        registry.vacuum()  # should not raise
        # Data should still be there
        assert len(registry.query_latest(limit=10)) == 5
