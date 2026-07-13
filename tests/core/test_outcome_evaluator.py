"""Tests for core.outcomes.evaluator — classification and evaluation logic."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from core.outcomes.evaluator import OutcomeEvaluator
from core.outcomes.model import OutcomeLabel
from core.outcomes.price_provider import CallbackPriceProvider, StaticPriceProvider
from core.outcomes.repository import OutcomeRepository


@pytest.fixture
def tmp_repo(tmp_path):
    """Create a temp OutcomeRepository."""
    return OutcomeRepository(str(tmp_path / "test_outcomes.db"))


@pytest.fixture
def evaluator(tmp_repo):
    """Create an evaluator with static price provider."""
    prices = StaticPriceProvider(price_map={"BTC/USDT": 50000.0})
    return OutcomeEvaluator(
        outcome_repo=tmp_repo,
        price_provider=prices,
        evaluation_window_seconds=3600,
        min_move_pct=0.5,
    )


def _make_signal(**overrides) -> dict[str, Any]:
    defaults = dict(
        id="sig-test-001",
        asset="BTC/USDT",
        direction="bullish",
        signal_class="entry",
        source="core.strategy",
        created_at=datetime.now(UTC) - timedelta(hours=2),
        confidence=0.7,
    )
    defaults.update(overrides)
    return defaults


class TestClassificationBullish:
    """Bullish signal classification."""

    def test_bullish_win_price_up(self, tmp_repo):
        """Bullish signal wins when price increases beyond threshold."""
        # Direct _classify test: bullish + +2% → WIN
        prices = StaticPriceProvider(price_map={"BTC/USDT": 51000.0})
        ev = OutcomeEvaluator(tmp_repo, prices, min_move_pct=0.5)
        label, score, reason = ev._classify("bullish", 2.0)
        assert label == OutcomeLabel.WIN
        assert score > 0
        assert "up" in reason

    def test_bullish_loss_price_down(self, tmp_repo):
        """Bullish signal loses when price decreases beyond threshold."""
        ev = OutcomeEvaluator(tmp_repo, StaticPriceProvider(), min_move_pct=0.5)
        label, score, reason = ev._classify("bullish", -2.0)
        assert label == OutcomeLabel.LOSS
        assert score < 0
        assert "down" in reason

    def test_bullish_neutral_small_move(self, tmp_repo):
        """Bullish signal neutral when move is below threshold."""
        ev = OutcomeEvaluator(tmp_repo, StaticPriceProvider(), min_move_pct=0.5)
        label, score, reason = ev._classify("bullish", 0.2)
        assert label == OutcomeLabel.NEUTRAL
        assert score == 0.0


class TestClassificationBearish:
    """Bearish signal classification."""

    def test_bearish_win_price_down(self, tmp_repo):
        ev = OutcomeEvaluator(tmp_repo, StaticPriceProvider(), min_move_pct=0.5)
        label, score, reason = ev._classify("bearish", -2.0)
        assert label == OutcomeLabel.WIN
        assert score > 0
        assert "down" in reason

    def test_bearish_loss_price_up(self, tmp_repo):
        ev = OutcomeEvaluator(tmp_repo, StaticPriceProvider(), min_move_pct=0.5)
        label, score, reason = ev._classify("bearish", 2.0)
        assert label == OutcomeLabel.LOSS
        assert score < 0
        assert "up" in reason

    def test_bearish_neutral_small_move(self, tmp_repo):
        ev = OutcomeEvaluator(tmp_repo, StaticPriceProvider(), min_move_pct=0.5)
        label, score, reason = ev._classify("bearish", -0.1)
        assert label == OutcomeLabel.NEUTRAL
        assert score == 0.0


class TestClassificationNeutral:
    """Neutral/unknown direction classification."""

    def test_neutral_direction_always_neutral(self, tmp_repo):
        ev = OutcomeEvaluator(tmp_repo, StaticPriceProvider(), min_move_pct=0.5)
        label, score, reason = ev._classify("neutral", 5.0)
        assert label == OutcomeLabel.NEUTRAL
        assert score == 0.0

    def test_unknown_direction_always_neutral(self, tmp_repo):
        ev = OutcomeEvaluator(tmp_repo, StaticPriceProvider(), min_move_pct=0.5)
        label, score, reason = ev._classify("unknown", -10.0)
        assert label == OutcomeLabel.NEUTRAL


class TestEvaluateSignal:
    """Full signal evaluation pipeline."""

    def test_evaluate_with_both_prices(self, tmp_repo):
        """Normal evaluation: entry + outcome prices available."""
        emitted_time = datetime.now(UTC) - timedelta(hours=2)

        def price_cb(asset, at_time):
            if at_time <= emitted_time + timedelta(seconds=10):
                return 50000.0
            return 51000.0

        prices = CallbackPriceProvider(price_cb)
        ev = OutcomeEvaluator(tmp_repo, prices, evaluation_window_seconds=3600, min_move_pct=0.5)

        signal = _make_signal(created_at=emitted_time)
        result = ev.evaluate_signal(signal)

        assert result is not None
        assert result.signal_id == "sig-test-001"
        assert result.entry_price == 50000.0
        assert result.outcome_price == 51000.0
        assert result.price_change_pct == pytest.approx(2.0)
        assert result.outcome_label == OutcomeLabel.WIN

    def test_evaluate_no_entry_price(self, tmp_repo):
        """Missing entry price → UNKNOWN outcome."""
        prices = CallbackPriceProvider(lambda asset, t: None)
        ev = OutcomeEvaluator(tmp_repo, prices)
        signal = _make_signal()
        result = ev.evaluate_signal(signal)
        assert result is not None
        assert result.outcome_label == OutcomeLabel.UNKNOWN
        assert result.reason == "no_entry_price"

    def test_evaluate_zero_entry_price(self, tmp_repo):
        """Zero entry price → UNKNOWN."""
        prices = StaticPriceProvider(price_map={"BTC/USDT": 0.0})
        ev = OutcomeEvaluator(tmp_repo, prices)
        signal = _make_signal()
        result = ev.evaluate_signal(signal)
        assert result is not None
        assert result.outcome_label == OutcomeLabel.UNKNOWN

    def test_evaluate_no_outcome_price(self, tmp_repo):
        """Missing outcome price → UNKNOWN."""
        emitted_time = datetime.now(UTC) - timedelta(hours=2)

        def price_cb(asset, at_time):
            if at_time <= emitted_time + timedelta(seconds=10):
                return 50000.0
            return None  # No price at eval time

        prices = CallbackPriceProvider(price_cb)
        ev = OutcomeEvaluator(tmp_repo, prices)
        signal = _make_signal(created_at=emitted_time)
        result = ev.evaluate_signal(signal)
        assert result is not None
        assert result.outcome_label == OutcomeLabel.UNKNOWN
        assert result.reason == "no_outcome_price"

    def test_evaluate_expired_when_max_age_passes_without_resolution(self, tmp_repo):
        emitted_at = datetime.now(UTC) - timedelta(hours=2)

        def price_cb(asset, at_time):
            return 50000.0 if at_time == emitted_at else None

        ev = OutcomeEvaluator(tmp_repo, CallbackPriceProvider(price_cb))
        result = ev.evaluate_signal(
            _make_signal(
                created_at=emitted_at,
                invalidation={"max_age_seconds": 60},
            )
        )

        assert result is not None
        assert result.outcome_label == OutcomeLabel.EXPIRED
        assert result.reason == "max_age_exceeded"

    def test_idempotent_duplicate_prevention(self, tmp_repo):
        """Running evaluate twice on same signal → skipped."""
        emitted_time = datetime.now(UTC) - timedelta(hours=2)

        def price_cb(asset, at_time):
            if at_time <= emitted_time + timedelta(seconds=10):
                return 50000.0
            return 51000.0

        prices = CallbackPriceProvider(price_cb)
        ev = OutcomeEvaluator(tmp_repo, prices)
        signal = _make_signal(created_at=emitted_time)

        # First evaluation + persist
        result1 = ev.evaluate_signal(signal)
        assert result1 is not None
        tmp_repo.upsert(result1)

        # Second evaluation → None (already has outcome)
        result2 = ev.evaluate_signal(signal)
        assert result2 is None

    def test_evaluate_signal_no_id(self, tmp_repo):
        """Signal without id → None."""
        ev = OutcomeEvaluator(tmp_repo, StaticPriceProvider())
        result = ev.evaluate_signal({"asset": "BTC/USDT"})
        assert result is None

    def test_evaluate_signal_no_created_at(self, tmp_repo):
        """Signal without valid created_at → None."""
        ev = OutcomeEvaluator(tmp_repo, StaticPriceProvider())
        result = ev.evaluate_signal({"id": "sig-1", "asset": "BTC/USDT", "created_at": ""})
        assert result is None


class TestEvaluateBatch:
    """Batch evaluation."""

    def test_batch_mixed_results(self, tmp_repo):
        """Batch processes multiple signals."""
        emitted_time = datetime.now(UTC) - timedelta(hours=3)

        def price_cb(asset, at_time):
            if at_time <= emitted_time + timedelta(seconds=10):
                return 50000.0
            return None  # No outcome price

        prices = CallbackPriceProvider(price_cb)
        ev = OutcomeEvaluator(tmp_repo, prices)

        signals = [
            _make_signal(id="batch-1", created_at=emitted_time),
            _make_signal(id="batch-2", created_at=emitted_time),
        ]
        stats = ev.evaluate_batch(signals, dry_run=False)
        assert stats["evaluated"] == 2

    def test_batch_dry_run_no_persist(self, tmp_repo):
        """Dry-run mode evaluates but doesn't persist."""
        emitted_time = datetime.now(UTC) - timedelta(hours=2)

        def price_cb(asset, at_time):
            return 50000.0

        prices = CallbackPriceProvider(price_cb)
        ev = OutcomeEvaluator(tmp_repo, prices)
        signals = [_make_signal(id="dry-1", created_at=emitted_time)]
        stats = ev.evaluate_batch(signals, dry_run=True)
        assert stats["evaluated"] == 1
        # Not persisted
        assert not tmp_repo.has_outcome("dry-1")
