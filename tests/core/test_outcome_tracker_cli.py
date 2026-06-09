"""Tests for CLI entry point and registry query_open."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from core.outcome_tracker import run as tracker_run
from core.outcomes.price_provider import StaticPriceProvider
from core.outcomes.repository import OutcomeRepository
from core.signals.envelope import (
    CanonicalSignalEnvelope,
    DataQuality,
    DataQualityStatus,
    SignalClass,
    SignalDirection,
    SignalPriority,
)
from core.signals.registry import CanonicalSignalRegistry


def _make_envelope(**overrides):
    defaults = dict(
        signal_class=SignalClass.ENTRY,
        subtype="test",
        source="test",
        asset="BTC/USDT",
        direction=SignalDirection.BULLISH,
        confidence=0.8,
        risk_score=0.2,
        priority=SignalPriority.MEDIUM,
        data_quality=DataQuality(status=DataQualityStatus.OK),
        actionability={"can_alert": True},
    )
    defaults.update(overrides)
    return CanonicalSignalEnvelope(**defaults)


class TestQueryOpen:
    """CanonicalSignalRegistry.query_open() — signals ready for evaluation."""

    def test_finds_old_emitted_signals(self, tmp_path):
        registry = CanonicalSignalRegistry(str(tmp_path / "signals.db"))
        # Insert a signal 2h ago
        env = _make_envelope()
        registry.append(env)
        # Manually set created_at to 2h ago by inserting directly
        two_hours_ago = str(datetime.now(UTC) - timedelta(hours=2))
        with registry._lock:
            registry._conn.execute(
                "UPDATE canonical_signals SET created_at = ? WHERE id = ?",
                (two_hours_ago, env.id),
            )
            registry._conn.commit()

        open_signals = registry.query_open(min_age_seconds=3600)
        assert len(open_signals) == 1
        assert open_signals[0]["id"] == env.id

    def test_skips_recent_signals(self, tmp_path):
        registry = CanonicalSignalRegistry(str(tmp_path / "signals.db"))
        env = _make_envelope()
        registry.append(env)
        # Signal is fresh — should not appear
        open_signals = registry.query_open(min_age_seconds=3600)
        assert len(open_signals) == 0

    def test_skips_expired_signals(self, tmp_path):
        registry = CanonicalSignalRegistry(str(tmp_path / "signals.db"))
        env = _make_envelope()
        registry.append(env)
        # Expire it
        from core.signals.registry import SignalLifecycle
        registry.transition(env.id, SignalLifecycle.EXPIRED, "too_old")
        # Set old timestamp
        two_hours_ago = str(datetime.now(UTC) - timedelta(hours=2))
        with registry._lock:
            registry._conn.execute(
                "UPDATE canonical_signals SET created_at = ? WHERE id = ?",
                (two_hours_ago, env.id),
            )
            registry._conn.commit()

        open_signals = registry.query_open(min_age_seconds=3600)
        assert len(open_signals) == 0

    def test_respects_limit(self, tmp_path):
        registry = CanonicalSignalRegistry(str(tmp_path / "signals.db"))
        two_hours_ago = str(datetime.now(UTC) - timedelta(hours=2))
        for i in range(5):
            env = _make_envelope(asset=f"ASSET{i}")
            registry.append(env)
            with registry._lock:
                registry._conn.execute(
                    "UPDATE canonical_signals SET created_at = ? WHERE id = ?",
                    (two_hours_ago, env.id),
                )
        with registry._lock:
            registry._conn.commit()

        open_signals = registry.query_open(min_age_seconds=3600, limit=3)
        assert len(open_signals) == 3

    def test_filter_by_signal_class(self, tmp_path):
        registry = CanonicalSignalRegistry(str(tmp_path / "signals.db"))
        two_hours_ago = str(datetime.now(UTC) - timedelta(hours=2))

        entry = _make_envelope(signal_class=SignalClass.ENTRY)
        risk = _make_envelope(signal_class=SignalClass.RISK, asset="ETH/USDT")
        registry.append(entry)
        registry.append(risk)
        with registry._lock:
            registry._conn.execute(
                "UPDATE canonical_signals SET created_at = ?",
                (two_hours_ago,),
            )
            registry._conn.commit()

        open_signals = registry.query_open(min_age_seconds=3600, signal_class=SignalClass.ENTRY)
        assert len(open_signals) == 1
        assert open_signals[0]["signal_class"] == "entry"


class TestCLIRunner:
    """CLI runner — python -m core.outcome_tracker equivalent."""

    def test_cli_no_open_signals(self, tmp_path):
        """No signals to evaluate → clean exit."""
        signal_db = str(tmp_path / "signals.db")
        outcome_db = str(tmp_path / "outcomes.db")
        registry = CanonicalSignalRegistry(signal_db)
        # No signals inserted

        result = tracker_run(
            db_path=outcome_db,
            signal_db_path=signal_db,
            _signal_registry=registry,
        )
        assert result["evaluated"] == 0
        assert result["total_open"] == 0

    def test_cli_with_evaluable_signals(self, tmp_path):
        """Signals exist, evaluation runs."""
        signal_db = str(tmp_path / "signals.db")
        outcome_db = str(tmp_path / "outcomes.db")
        registry = CanonicalSignalRegistry(signal_db)

        # Insert old signal
        env = _make_envelope()
        registry.append(env)
        two_hours_ago = str(datetime.now(UTC) - timedelta(hours=2))
        with registry._lock:
            registry._conn.execute(
                "UPDATE canonical_signals SET created_at = ? WHERE id = ?",
                (two_hours_ago, env.id),
            )
            registry._conn.commit()

        # Static prices
        prices = StaticPriceProvider(price_map={"BTC/USDT": 50000.0})

        result = tracker_run(
            db_path=outcome_db,
            signal_db_path=signal_db,
            price_provider=prices,
            _signal_registry=registry,
        )
        assert result["total_open"] == 1
        assert result["evaluated"] == 1

        # Verify persisted
        outcome_repo = OutcomeRepository(outcome_db)
        assert outcome_repo.has_outcome(env.id)

    def test_cli_dry_run(self, tmp_path):
        """Dry run evaluates but doesn't persist."""
        signal_db = str(tmp_path / "signals.db")
        outcome_db = str(tmp_path / "outcomes.db")
        registry = CanonicalSignalRegistry(signal_db)

        env = _make_envelope()
        registry.append(env)
        two_hours_ago = str(datetime.now(UTC) - timedelta(hours=2))
        with registry._lock:
            registry._conn.execute(
                "UPDATE canonical_signals SET created_at = ? WHERE id = ?",
                (two_hours_ago, env.id),
            )
            registry._conn.commit()

        prices = StaticPriceProvider(price_map={"BTC/USDT": 50000.0})

        result = tracker_run(
            db_path=outcome_db,
            signal_db_path=signal_db,
            dry_run=True,
            price_provider=prices,
            _signal_registry=registry,
        )
        assert result["evaluated"] == 1

        # Not persisted
        outcome_repo = OutcomeRepository(outcome_db)
        assert not outcome_repo.has_outcome(env.id)

    def test_cli_idempotent_rerun(self, tmp_path):
        """Running twice on same signals skips already evaluated."""
        signal_db = str(tmp_path / "signals.db")
        outcome_db = str(tmp_path / "outcomes.db")
        registry = CanonicalSignalRegistry(signal_db)

        env = _make_envelope()
        registry.append(env)
        two_hours_ago = str(datetime.now(UTC) - timedelta(hours=2))
        with registry._lock:
            registry._conn.execute(
                "UPDATE canonical_signals SET created_at = ? WHERE id = ?",
                (two_hours_ago, env.id),
            )
            registry._conn.commit()

        prices = StaticPriceProvider(price_map={"BTC/USDT": 50000.0})

        # First run
        r1 = tracker_run(
            db_path=outcome_db,
            signal_db_path=signal_db,
            price_provider=prices,
            _signal_registry=registry,
        )
        assert r1["evaluated"] == 1

        # Second run — evaluator skips already-evaluated signals
        r2 = tracker_run(
            db_path=outcome_db,
            signal_db_path=signal_db,
            price_provider=prices,
            _signal_registry=registry,
        )
        # Signals still show up as open, but evaluator skips them
        assert r2["total_open"] == 1
        assert r2["skipped"] == 1
