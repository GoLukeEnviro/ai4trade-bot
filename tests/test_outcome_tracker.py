# tests/test_outcome_tracker.py
"""Tests for core.outcome_tracker.OutcomeTracker and storage outcome methods."""

from __future__ import annotations

from core.outcome_tracker import OutcomeTracker
from core.signal_model import Signal
from storage.sqlite_repository import SqliteSignalRepository


def _make_signal(action: str = "BUY", price: float = 50000.0) -> Signal:
    return Signal(pair="BTC/USDT", action=action, confidence=75, price=price, quantity=0.1)


class TestOutcomeRepository:
    def test_log_signal_with_id_returns_uuid(self) -> None:
        repo = SqliteSignalRepository(":memory:")
        signal = _make_signal()
        signal_id = repo.log_signal_with_id(signal)
        assert len(signal_id) == 36  # UUID format
        repo.close()

    def test_get_pending_outcomes_empty(self) -> None:
        repo = SqliteSignalRepository(":memory:")
        pending = repo.get_pending_outcomes()
        assert pending == []
        repo.close()

    def test_update_outcome(self) -> None:
        repo = SqliteSignalRepository(":memory:")
        signal = _make_signal()
        signal_id = repo.log_signal_with_id(signal)

        repo.update_outcome(signal_id, exit_price=52000.0, outcome=1)

        outcomes = repo.get_outcomes_for_training()
        assert len(outcomes) == 1
        assert outcomes[0]["outcome"] == 1
        assert outcomes[0]["exit_price"] == 52000.0
        repo.close()

    def test_get_outcomes_for_training_filters_unresolved(self) -> None:
        repo = SqliteSignalRepository(":memory:")
        sig1 = _make_signal(action="BUY", price=50000.0)
        sig2 = _make_signal(action="SELL", price=48000.0)
        id1 = repo.log_signal_with_id(sig1)
        repo.log_signal_with_id(sig2)

        repo.update_outcome(id1, exit_price=52000.0, outcome=1)

        outcomes = repo.get_outcomes_for_training()
        assert len(outcomes) == 1
        assert outcomes[0]["signal_id"] == id1
        repo.close()

    def test_get_outcomes_for_training_by_pair(self) -> None:
        repo = SqliteSignalRepository(":memory:")
        sig1 = Signal(pair="BTC/USDT", action="BUY", confidence=75, price=50000.0, quantity=0.1)
        sig2 = Signal(pair="ETH/USDT", action="BUY", confidence=70, price=3000.0, quantity=1.0)
        id1 = repo.log_signal_with_id(sig1)
        id2 = repo.log_signal_with_id(sig2)

        repo.update_outcome(id1, exit_price=52000.0, outcome=1)
        repo.update_outcome(id2, exit_price=2800.0, outcome=0)

        btc = repo.get_outcomes_for_training(pair="BTC/USDT")
        assert len(btc) == 1
        assert btc[0]["outcome"] == 1
        repo.close()


class TestOutcomeTracker:
    def test_evaluate_buy_correct(self) -> None:
        repo = SqliteSignalRepository(":memory:")
        tracker = OutcomeTracker(
            repository=repo,
            outcome_window_hours=0.0,
            check_interval_seconds=1.0,
            get_price_fn=lambda pair: 52000.0,  # Price went up
        )
        _make_signal(action="BUY", price=50000.0)
        entry = {"signal_id": "test-1", "pair": "BTC/USDT", "action": "BUY", "entry_price": 50000.0}
        result = tracker._evaluate_outcome(entry)
        assert result is not None
        assert result["outcome"] == 1
        assert result["exit_price"] == 52000.0
        repo.close()

    def test_evaluate_buy_incorrect(self) -> None:
        repo = SqliteSignalRepository(":memory:")
        tracker = OutcomeTracker(
            repository=repo,
            outcome_window_hours=0.0,
            check_interval_seconds=1.0,
            get_price_fn=lambda pair: 48000.0,  # Price went down
        )
        entry = {"signal_id": "test-2", "pair": "BTC/USDT", "action": "BUY", "entry_price": 50000.0}
        result = tracker._evaluate_outcome(entry)
        assert result is not None
        assert result["outcome"] == 0
        repo.close()

    def test_evaluate_sell_correct(self) -> None:
        repo = SqliteSignalRepository(":memory:")
        tracker = OutcomeTracker(
            repository=repo,
            outcome_window_hours=0.0,
            check_interval_seconds=1.0,
            get_price_fn=lambda pair: 48000.0,  # Price went down — correct for SELL
        )
        entry = {"signal_id": "test-3", "pair": "BTC/USDT", "action": "SELL", "entry_price": 50000.0}
        result = tracker._evaluate_outcome(entry)
        assert result is not None
        assert result["outcome"] == 1
        repo.close()

    def test_evaluate_sell_incorrect(self) -> None:
        repo = SqliteSignalRepository(":memory:")
        tracker = OutcomeTracker(
            repository=repo,
            outcome_window_hours=0.0,
            check_interval_seconds=1.0,
            get_price_fn=lambda pair: 52000.0,  # Price went up — incorrect for SELL
        )
        entry = {"signal_id": "test-4", "pair": "BTC/USDT", "action": "SELL", "entry_price": 50000.0}
        result = tracker._evaluate_outcome(entry)
        assert result is not None
        assert result["outcome"] == 0
        repo.close()

    def test_evaluate_price_fetch_failure(self) -> None:
        repo = SqliteSignalRepository(":memory:")
        tracker = OutcomeTracker(
            repository=repo,
            outcome_window_hours=0.0,
            check_interval_seconds=1.0,
            get_price_fn=lambda pair: (_ for _ in ()).throw(Exception("network error")),
        )
        entry = {"signal_id": "test-5", "pair": "BTC/USDT", "action": "BUY", "entry_price": 50000.0}
        result = tracker._evaluate_outcome(entry)
        assert result is None
        repo.close()

    def test_evaluate_hold_signal(self) -> None:
        repo = SqliteSignalRepository(":memory:")
        tracker = OutcomeTracker(
            repository=repo,
            outcome_window_hours=0.0,
            check_interval_seconds=1.0,
            get_price_fn=lambda pair: 52000.0,
        )
        entry = {"signal_id": "test-6", "pair": "BTC/USDT", "action": "HOLD", "entry_price": 50000.0}
        result = tracker._evaluate_outcome(entry)
        assert result is not None
        assert result["outcome"] == 0  # HOLD is never a correct "trade"
        repo.close()

    def test_tracker_can_start_and_stop(self) -> None:
        repo = SqliteSignalRepository(":memory:")
        tracker = OutcomeTracker(
            repository=repo,
            outcome_window_hours=4.0,
            check_interval_seconds=60.0,
        )
        tracker.start()
        tracker.stop()
        repo.close()
