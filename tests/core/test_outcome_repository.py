"""Tests for core.outcomes.repository — SQLite persistence."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from core.outcomes.model import OutcomeLabel, SignalOutcome
from core.outcomes.repository import OutcomeRepository


@pytest.fixture
def repo(tmp_path):
    return OutcomeRepository(str(tmp_path / "test_outcomes.db"))


def _make_outcome(**overrides):
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


class TestOutcomeRepositoryInsert:
    """Insert and retrieve outcomes."""

    def test_insert_and_get(self, repo):
        o = _make_outcome()
        repo.insert(o)
        result = repo.get_by_signal_id("sig-001")
        assert result is not None
        assert result.signal_id == "sig-001"
        assert result.asset == "BTC/USDT"
        assert result.outcome_label == OutcomeLabel.WIN
        assert result.entry_price == 50000.0
        assert result.outcome_price == 51000.0

    def test_insert_duplicate_raises(self, repo):
        o = _make_outcome()
        repo.insert(o)
        with pytest.raises(Exception):
            repo.insert(o)

    def test_has_outcome_true(self, repo):
        repo.insert(_make_outcome())
        assert repo.has_outcome("sig-001") is True

    def test_has_outcome_false(self, repo):
        assert repo.has_outcome("nonexistent") is False


class TestOutcomeRepositoryUpsert:
    """Upsert (insert or update)."""

    def test_upsert_insert(self, repo):
        o = _make_outcome()
        repo.upsert(o)
        assert repo.has_outcome("sig-001")

    def test_upsert_update(self, repo):
        o = _make_outcome(outcome_label=OutcomeLabel.UNKNOWN, outcome_score=0.0)
        repo.upsert(o)
        assert repo.get_by_signal_id("sig-001").outcome_label == OutcomeLabel.UNKNOWN

        # Update
        o2 = _make_outcome(outcome_label=OutcomeLabel.WIN, outcome_score=0.9)
        repo.upsert(o2)
        result = repo.get_by_signal_id("sig-001")
        assert result.outcome_label == OutcomeLabel.WIN
        assert result.outcome_score == 0.9


class TestOutcomeRepositoryQuery:
    """Query with filters."""

    def test_query_all(self, repo):
        repo.insert(_make_outcome(signal_id="s1", asset="BTC/USDT"))
        repo.insert(_make_outcome(signal_id="s2", asset="ETH/USDT"))
        results = repo.query()
        assert len(results) == 2

    def test_query_by_asset(self, repo):
        repo.insert(_make_outcome(signal_id="s1", asset="BTC/USDT"))
        repo.insert(_make_outcome(signal_id="s2", asset="ETH/USDT"))
        results = repo.query(asset="BTC/USDT")
        assert len(results) == 1
        assert results[0].asset == "BTC/USDT"

    def test_query_by_label(self, repo):
        repo.insert(_make_outcome(signal_id="s1", outcome_label=OutcomeLabel.WIN))
        repo.insert(_make_outcome(signal_id="s2", outcome_label=OutcomeLabel.LOSS))
        results = repo.query(outcome_label=OutcomeLabel.WIN)
        assert len(results) == 1
        assert results[0].outcome_label == OutcomeLabel.WIN

    def test_query_with_limit(self, repo):
        for i in range(10):
            repo.insert(_make_outcome(signal_id=f"s-{i}"))
        results = repo.query(limit=5)
        assert len(results) == 5

    def test_count_all(self, repo):
        repo.insert(_make_outcome(signal_id="s1"))
        repo.insert(_make_outcome(signal_id="s2"))
        assert repo.count() == 2

    def test_count_by_label(self, repo):
        repo.insert(_make_outcome(signal_id="s1", outcome_label=OutcomeLabel.WIN))
        repo.insert(_make_outcome(signal_id="s2", outcome_label=OutcomeLabel.LOSS))
        assert repo.count(outcome_label=OutcomeLabel.WIN) == 1

    def test_get_nonexistent(self, repo):
        assert repo.get_by_signal_id("nope") is None


class TestOutcomeRepositoryExport:
    """Export for training."""

    def test_export_all(self, repo):
        repo.insert(_make_outcome(signal_id="s1"))
        repo.insert(_make_outcome(signal_id="s2"))
        data = repo.export_all()
        assert len(data) == 2
        assert isinstance(data[0], dict)
        assert "signal_id" in data[0]
        assert "outcome_label" in data[0]

    def test_export_empty(self, repo):
        data = repo.export_all()
        assert data == []


class TestOutcomeRepositoryExtra:
    """Extra/JSON fields preserved correctly."""

    def test_extra_json_preserved(self, repo):
        o = _make_outcome(extra={"market_regime": "trending", "volatility": 0.85})
        repo.insert(o)
        result = repo.get_by_signal_id("sig-001")
        assert result.extra["market_regime"] == "trending"
        assert result.extra["volatility"] == 0.85

    def test_close(self, repo):
        repo.close()
        # Should not raise
