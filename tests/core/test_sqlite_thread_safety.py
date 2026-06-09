"""Tests for SQLite write synchronization via threading.Lock (P1 hardening).

Verifies that:
- Concurrent writes do not crash (registry and outcomes repo)
- Write failures do not leave transactions open
- Existing registry/outcome/signal tests remain green (implicitly via the full suite)
- Database writes remain deterministic
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime

import pytest

from core.outcomes.model import OutcomeLabel, SignalOutcome
from core.outcomes.repository import OutcomeRepository
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


def _make_outcome(**overrides) -> SignalOutcome:
    defaults = dict(
        signal_id="sig-001",
        asset="BTC/USDT",
        direction="bullish",
        signal_class="entry",
        source="core.strategy",
        emitted_at=datetime.now(UTC),
        entry_price=50000.0,
        outcome_price=51000.0,
        price_change_pct=2.0,
        expected_direction="bullish",
        outcome_label=OutcomeLabel.WIN,
        outcome_score=0.8,
        reason="test",
        confidence_at_signal=0.7,
    )
    defaults.update(overrides)
    return SignalOutcome(**defaults)


# ======================================================================
# Canonical Signal Registry — concurrent write tests
# ======================================================================

class TestRegistryThreadSafety:
    """Concurrent writes to CanonicalSignalRegistry do not crash."""

    def test_concurrent_appends(self, tmp_path):
        """Multiple threads appending signals concurrently should not crash."""
        db_path = str(tmp_path / "test_registry.db")
        registry = CanonicalSignalRegistry(db_path=db_path)
        errors: list[Exception] = []

        def append_signal(idx: int) -> None:
            try:
                env = _make_envelope(asset=f"ASSET{idx}/USDT")
                registry.append(env)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=append_signal, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Errors during concurrent appends: {errors}"
        results = registry.query_latest(limit=50)
        assert len(results) == 20
        registry.close()

    def test_concurrent_transitions(self, tmp_path):
        """Multiple threads transitioning signal state concurrently."""
        db_path = str(tmp_path / "test_registry.db")
        registry = CanonicalSignalRegistry(db_path=db_path)

        # Insert signals first
        ids = []
        for i in range(10):
            env = _make_envelope(asset=f"ASSET{i}/USDT")
            registry.append(env)
            ids.append(env.id)

        errors: list[Exception] = []

        def transition_signal(signal_id: str) -> None:
            try:
                registry.transition(signal_id, SignalLifecycle.EXPIRED, "concurrent_test")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=transition_signal, args=(sid,)) for sid in ids]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Errors during concurrent transitions: {errors}"
        registry.close()

    def test_concurrent_reads_and_writes(self, tmp_path):
        """Reads and writes happening concurrently should not crash."""
        db_path = str(tmp_path / "test_registry.db")
        registry = CanonicalSignalRegistry(db_path=db_path)

        # Pre-populate some data
        for i in range(5):
            env = _make_envelope(asset=f"BASE{i}/USDT")
            registry.append(env)

        errors: list[Exception] = []
        read_results: dict[int, int] = {}

        def writer(idx: int) -> None:
            try:
                env = _make_envelope(asset=f"WRITER{idx}/USDT")
                registry.append(env)
            except Exception as e:
                errors.append(e)

        def reader(idx: int) -> None:
            try:
                results = registry.query_latest(limit=100)
                read_results[idx] = len(results)
            except Exception as e:
                errors.append(e)

        threads = (
            [threading.Thread(target=writer, args=(i,)) for i in range(10)]
            + [threading.Thread(target=reader, args=(i,)) for i in range(10)]
        )
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Errors during concurrent reads/writes: {errors}"
        # At least the initial 5 signals should be readable
        total = registry.query_latest(limit=100)
        assert len(total) >= 5
        registry.close()


# ======================================================================
# Outcome Repository — concurrent write tests
# ======================================================================

class TestOutcomeRepositoryThreadSafety:
    """Concurrent writes to OutcomeRepository do not crash."""

    def test_concurrent_inserts(self, tmp_path):
        """Multiple threads inserting outcomes concurrently should not crash."""
        db_path = str(tmp_path / "test_outcomes.db")
        repo = OutcomeRepository(db_path=db_path)
        errors: list[Exception] = []

        def insert_outcome(idx: int) -> None:
            try:
                o = _make_outcome(signal_id=f"sig-{idx}", asset=f"ASSET{idx}/USDT")
                repo.insert(o)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=insert_outcome, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Errors during concurrent inserts: {errors}"
        assert repo.count() == 20
        repo.close()

    def test_concurrent_upserts(self, tmp_path):
        """Multiple threads upserting the same signal id concurrently should not crash."""
        db_path = str(tmp_path / "test_outcomes.db")
        repo = OutcomeRepository(db_path=db_path)
        errors: list[Exception] = []

        def upsert_outcome(idx: int) -> None:
            try:
                o = _make_outcome(
                    signal_id="shared-sig",
                    outcome_score=float(idx) / 20.0,
                )
                repo.upsert(o)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=upsert_outcome, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Errors during concurrent upserts: {errors}"
        # Only one row should exist (upsert = insert or update)
        assert repo.count() == 1
        repo.close()

    def test_write_failure_does_not_leave_transaction_open(self, tmp_path):
        """If an insert fails (e.g. duplicate), subsequent operations should still work."""
        db_path = str(tmp_path / "test_outcomes.db")
        repo = OutcomeRepository(db_path=db_path)

        o = _make_outcome(signal_id="unique-sig")
        repo.insert(o)

        # Inserting again should raise (duplicate primary key)
        with pytest.raises(Exception):
            repo.insert(o)

        # Repository should still be usable
        o2 = _make_outcome(signal_id="another-sig", asset="ETH/USDT")
        repo.insert(o2)
        assert repo.count() == 2

        repo.close()


# ======================================================================
# Registry — rollback on write failure
# ======================================================================

class TestRegistryRollbackOnWriteFailure:
    """Verify that write failures don't leave transactions open."""

    def test_duplicate_insert_does_not_corrupt(self, tmp_path):
        """Inserting a duplicate should not corrupt the database or leave it locked."""
        db_path = str(tmp_path / "test_registry.db")
        registry = CanonicalSignalRegistry(db_path=db_path)

        env = _make_envelope(asset="BTC/USDT")
        registry.append(env)

        # Try to insert the same signal again (same id) — should raise
        with pytest.raises(Exception):
            registry.append(env)

        # Registry should still be functional
        env2 = _make_envelope(asset="ETH/USDT")
        registry.append(env2)
        results = registry.query_latest(limit=10)
        assert len(results) == 2
        registry.close()
