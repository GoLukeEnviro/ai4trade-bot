"""Tests for core.outcomes.model — OutcomeLabel, SignalOutcome, safety invariants."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from core.outcomes.model import OutcomeLabel, SignalOutcome


class TestOutcomeLabel:
    """OutcomeLabel enum values."""

    def test_all_labels_exist(self):
        assert OutcomeLabel.WIN == "win"
        assert OutcomeLabel.LOSS == "loss"
        assert OutcomeLabel.NEUTRAL == "neutral"
        assert OutcomeLabel.EXPIRED == "expired"
        assert OutcomeLabel.UNKNOWN == "unknown"

    def test_label_count(self):
        assert len(OutcomeLabel) == 5


class TestSignalOutcome:
    """SignalOutcome model validation."""

    def _make_outcome(self, **overrides):
        defaults = dict(
            signal_id="sig-001",
            asset="BTC/USDT",
            direction="bullish",
            signal_class="entry",
            source="core.strategy",
            emitted_at=datetime.now(UTC),
            evaluation_window_seconds=3600,
            entry_price=50000.0,
            outcome_price=51000.0,
            price_change_pct=2.0,
            expected_direction="bullish",
            outcome_label=OutcomeLabel.WIN,
            outcome_score=0.8,
            reason="price_moved_up",
        )
        defaults.update(overrides)
        return SignalOutcome(**defaults)

    def test_basic_creation(self):
        o = self._make_outcome()
        assert o.signal_id == "sig-001"
        assert o.asset == "BTC/USDT"
        assert o.direction == "bullish"
        assert o.outcome_label == OutcomeLabel.WIN

    def test_evaluated_at_auto_set(self):
        o = self._make_outcome()
        assert o.evaluated_at is not None
        assert isinstance(o.evaluated_at, datetime)

    def test_optional_fields_none(self):
        o = self._make_outcome(entry_price=None, outcome_price=None, price_change_pct=None)
        assert o.entry_price is None
        assert o.outcome_price is None
        assert o.price_change_pct is None

    def test_confidence_at_signal_optional(self):
        o = self._make_outcome(confidence_at_signal=None)
        assert o.confidence_at_signal is None

    def test_confidence_at_signal_set(self):
        o = self._make_outcome(confidence_at_signal=0.85)
        assert o.confidence_at_signal == 0.85

    def test_extra_fields_default_empty(self):
        o = self._make_outcome()
        assert o.extra == {}

    def test_extra_fields_custom(self):
        o = self._make_outcome(extra={"market_regime": "trending", "volume_ratio": 1.5})
        assert o.extra["market_regime"] == "trending"

    def test_outcome_score_bounds_low(self):
        o = self._make_outcome(outcome_score=-1.0)
        assert o.outcome_score == -1.0

    def test_outcome_score_bounds_high(self):
        o = self._make_outcome(outcome_score=1.0)
        assert o.outcome_score == 1.0

    def test_outcome_score_rejects_out_of_range(self):
        with pytest.raises(Exception):
            self._make_outcome(outcome_score=1.5)

    def test_outcome_score_rejects_below_range(self):
        with pytest.raises(Exception):
            self._make_outcome(outcome_score=-1.5)

    def test_default_label_unknown(self):
        o = self._make_outcome(outcome_label=OutcomeLabel.UNKNOWN)
        assert o.outcome_label == OutcomeLabel.UNKNOWN

    def test_serialization_round_trip(self):
        o = self._make_outcome()
        data = o.model_dump(mode="json")
        o2 = SignalOutcome(**data)
        assert o2.signal_id == o.signal_id
        assert o2.outcome_label == o.outcome_label


class TestSafetyInvariants:
    """Outcome tracking must NEVER enable trading or strategy changes."""

    def test_no_execution_capability(self):
        """SignalOutcome has no execute/trade/strategy fields."""
        o = SignalOutcome(
            signal_id="safe-test",
            asset="BTC/USDT",
            direction="bullish",
            signal_class="entry",
            emitted_at=datetime.now(UTC),
        )
        assert not hasattr(o, "can_execute")
        assert not hasattr(o, "execute")
        assert not hasattr(o, "trade")
        assert not hasattr(o, "strategy_modulation")

    def test_cannot_import_live_trading_from_outcomes(self):
        """Importing outcomes should never bring in trading dependencies."""
        import core.outcomes
        assert not hasattr(core.outcomes, "execute_trade")
        assert not hasattr(core.outcomes, "place_order")

    def test_observational_only(self):
        """Outcome is a data record, not an action."""
        o = SignalOutcome(
            signal_id="obs-test",
            asset="ETH/USDT",
            direction="bearish",
            signal_class="entry",
            emitted_at=datetime.now(UTC),
            outcome_label=OutcomeLabel.LOSS,
            outcome_score=-0.5,
            reason="price_moved_up",
        )
        # It's just data — no side effects possible
        assert isinstance(o, SignalOutcome)
        assert o.outcome_label == OutcomeLabel.LOSS
