"""Tests for core.db_maintenance CLI and method integration."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from core.db_maintenance import main as db_main
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
from core.signals.registry import CanonicalSignalRegistry

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
        reason="price_moved_up",
        confidence_at_signal=0.7,
    )
    defaults.update(overrides)
    return SignalOutcome(**defaults)


# ======================================================================
# Method-level tests (via temp DBs)
# ======================================================================


class TestRegistryCleanupExpired:
    def test_cleanup_expired_with_known_data(self, tmp_path):
        """Insert old data, run cleanup, verify deletion."""
        db = tmp_path / "reg.db"
        reg = CanonicalSignalRegistry(db_path=str(db))
        env = _make_envelope()
        old_time = datetime.now(UTC) - timedelta(hours=48)
        payload = env.model_dump(mode="json")
        payload["signal_class"] = payload.pop("class", payload.get("signal_class"))
        envelope_json = json.dumps(payload, default=str)
        with reg._lock:
            reg._conn.execute(
                "INSERT INTO canonical_signals "
                "(id, envelope_json, lifecycle, created_at, asset, signal_class, updated_at) "
                "VALUES (?, ?, 'emitted', ?, ?, ?, ?)",
                (env.id, envelope_json, str(old_time), env.asset, env.signal_class.value, str(old_time)),
            )
            reg._conn.commit()
        deleted = reg.cleanup_expired(max_age_hours=24)
        assert deleted == 1
        assert reg.get_signal(env.id) is None
        reg.close()

    def test_cleanup_expired_returns_correct_count(self, tmp_path):
        """Multiple old signals: verify count matches."""
        db = tmp_path / "reg.db"
        reg = CanonicalSignalRegistry(db_path=str(db))
        for i in range(5):
            env = _make_envelope(asset=f"COIN{i}/USDT")
            old_time = datetime.now(UTC) - timedelta(hours=48)
            payload = env.model_dump(mode="json")
            payload["signal_class"] = payload.pop("class", payload.get("signal_class"))
            envelope_json = json.dumps(payload, default=str)
            with reg._lock:
                reg._conn.execute(
                    "INSERT INTO canonical_signals "
                    "(id, envelope_json, lifecycle, created_at, asset, signal_class, updated_at) "
                    "VALUES (?, ?, 'emitted', ?, ?, ?, ?)",
                    (env.id, envelope_json, str(old_time), env.asset, env.signal_class.value, str(old_time)),
                )
                reg._conn.commit()
        deleted = reg.cleanup_expired(max_age_hours=24)
        assert deleted == 5
        reg.close()


class TestOutcomeCleanupOld:
    def test_cleanup_old_with_known_data(self, tmp_path):
        """Insert old outcome, run cleanup, verify deletion."""
        db = tmp_path / "out.db"
        repo = OutcomeRepository(db_path=str(db))
        old_eval = datetime.now(UTC) - timedelta(days=60)
        o = _make_outcome(evaluated_at=old_eval)
        repo.insert(o)
        deleted = repo.cleanup_old(max_age_days=30)
        assert deleted == 1
        assert repo.get_by_signal_id("sig-001") is None
        repo.close()

    def test_cleanup_old_returns_correct_count(self, tmp_path):
        """Multiple old outcomes: verify count matches."""
        db = tmp_path / "out.db"
        repo = OutcomeRepository(db_path=str(db))
        old_eval = datetime.now(UTC) - timedelta(days=60)
        for i in range(5):
            o = _make_outcome(signal_id=f"sig-{i}", evaluated_at=old_eval)
            repo.insert(o)
        deleted = repo.cleanup_old(max_age_days=30)
        assert deleted == 5
        repo.close()


class TestVacuumNoCrash:
    def test_registry_vacuum_no_crash(self, tmp_path):
        db = tmp_path / "reg.db"
        reg = CanonicalSignalRegistry(db_path=str(db))
        reg.append(_make_envelope())
        reg.vacuum()
        assert len(reg.query_latest(limit=10)) == 1
        reg.close()

    def test_outcome_vacuum_no_crash(self, tmp_path):
        db = tmp_path / "out.db"
        repo = OutcomeRepository(db_path=str(db))
        repo.insert(_make_outcome())
        repo.vacuum()
        assert repo.count() == 1
        repo.close()


class TestCleanupEmptyDB:
    def test_registry_cleanup_empty_returns_zero(self, tmp_path):
        db = tmp_path / "reg.db"
        reg = CanonicalSignalRegistry(db_path=str(db))
        assert reg.cleanup_expired(max_age_hours=24) == 0
        reg.close()

    def test_outcome_cleanup_empty_returns_zero(self, tmp_path):
        db = tmp_path / "out.db"
        repo = OutcomeRepository(db_path=str(db))
        assert repo.cleanup_old(max_age_days=30) == 0
        repo.close()


# ======================================================================
# CLI integration tests
# ======================================================================


class TestDBMaintenanceCLI:
    def test_all_flag_runs(self, tmp_path):
        """Running with --all should complete without error on temp DBs."""
        reg_db = tmp_path / "signals.db"
        out_db = tmp_path / "outcomes.db"
        # Create the DBs so the files exist
        reg = CanonicalSignalRegistry(db_path=str(reg_db))
        repo = OutcomeRepository(db_path=str(out_db))
        reg.append(_make_envelope())
        repo.insert(_make_outcome())
        reg.close()
        repo.close()

        with patch.dict(
            "os.environ",
            {},
        ):
            # Patch default paths to point at temp DBs
            with patch("core.db_maintenance._DEFAULT_REGISTRY_DB", str(reg_db)), \
                 patch("core.db_maintenance._DEFAULT_OUTCOMES_DB", str(out_db)):
                rc = db_main(["--all"])
        assert rc == 0

    def test_cli_exits_0_on_success(self, tmp_path):
        """CLI should exit 0 on success."""
        reg_db = tmp_path / "signals.db"
        out_db = tmp_path / "outcomes.db"
        CanonicalSignalRegistry(db_path=str(reg_db)).close()
        OutcomeRepository(db_path=str(out_db)).close()

        with patch("core.db_maintenance._DEFAULT_REGISTRY_DB", str(reg_db)), \
             patch("core.db_maintenance._DEFAULT_OUTCOMES_DB", str(out_db)):
            rc = db_main(["--vacuum"])
        assert rc == 0

    def test_cli_handles_missing_db(self, tmp_path):
        """CLI should not crash when DB files are missing."""
        nonexistent_reg = str(tmp_path / "no_signals.db")
        nonexistent_out = str(tmp_path / "no_outcomes.db")

        with patch("core.db_maintenance._DEFAULT_REGISTRY_DB", nonexistent_reg), \
             patch("core.db_maintenance._DEFAULT_OUTCOMES_DB", nonexistent_out):
            rc = db_main(["--all"])
        # Should succeed even if files don't exist (just skips)
        assert rc == 0

    def test_cli_cleanup_registry_only(self, tmp_path):
        """--cleanup-registry should only touch registry."""
        reg_db = tmp_path / "signals.db"
        out_db = tmp_path / "outcomes.db"
        reg = CanonicalSignalRegistry(db_path=str(reg_db))
        repo = OutcomeRepository(db_path=str(out_db))
        # Insert old data in registry
        env = _make_envelope()
        old_time = datetime.now(UTC) - timedelta(hours=48)
        payload = env.model_dump(mode="json")
        payload["signal_class"] = payload.pop("class", payload.get("signal_class"))
        envelope_json = json.dumps(payload, default=str)
        with reg._lock:
            reg._conn.execute(
                "INSERT INTO canonical_signals "
                "(id, envelope_json, lifecycle, created_at, asset, signal_class, updated_at) "
                "VALUES (?, ?, 'emitted', ?, ?, ?, ?)",
                (env.id, envelope_json, str(old_time), env.asset, env.signal_class.value, str(old_time)),
            )
            reg._conn.commit()
        repo.insert(_make_outcome())
        reg.close()
        repo.close()

        with patch("core.db_maintenance._DEFAULT_REGISTRY_DB", str(reg_db)), \
             patch("core.db_maintenance._DEFAULT_OUTCOMES_DB", str(out_db)):
            rc = db_main(["--cleanup-registry", "24"])
        assert rc == 0

    def test_cli_no_args_shows_help(self, capsys):
        """Running with no args should show help and exit 0."""
        rc = db_main([])
        assert rc == 0
