import json
import tempfile
import threading
from pathlib import Path

from core.signal_model import Signal
from storage.sqlite_repository import SqliteSignalRepository


def _make_signal(**overrides) -> Signal:
    defaults = dict(pair="BTC/USDT", action="BUY", confidence=75, price=65000.0, quantity=0.1)
    defaults.update(overrides)
    return Signal(**defaults)


def _repo_in_memory() -> SqliteSignalRepository:
    return SqliteSignalRepository(db_path=":memory:")


def test_save_signal_returns_id():
    repo = _repo_in_memory()
    row_id = repo.save_signal(_make_signal())
    assert row_id == 1
    repo.close()


def test_save_signal_with_trace_and_correlation_ids():
    repo = _repo_in_memory()
    repo.save_signal(_make_signal(), trace_id="t-1", correlation_id="c-1")
    rows = repo.get_recent_signals()
    assert rows[0]["trace_id"] == "t-1"
    assert rows[0]["correlation_id"] == "c-1"
    repo.close()


def test_get_recent_signals_returns_all():
    repo = _repo_in_memory()
    repo.save_signal(_make_signal(pair="BTC/USDT"))
    repo.save_signal(_make_signal(pair="ETH/USDT"))
    rows = repo.get_recent_signals()
    assert len(rows) == 2
    repo.close()


def test_get_recent_signals_filters_by_pair():
    repo = _repo_in_memory()
    repo.save_signal(_make_signal(pair="BTC/USDT"))
    repo.save_signal(_make_signal(pair="ETH/USDT"))
    rows = repo.get_recent_signals(pair="BTC/USDT")
    assert len(rows) == 1
    assert rows[0]["pair"] == "BTC/USDT"
    repo.close()


def test_get_recent_signals_respects_limit():
    repo = _repo_in_memory()
    for i in range(10):
        repo.save_signal(_make_signal(confidence=70 + i))
    rows = repo.get_recent_signals(limit=3)
    assert len(rows) == 3
    repo.close()


def test_get_recent_signals_empty_db():
    repo = _repo_in_memory()
    rows = repo.get_recent_signals()
    assert rows == []
    repo.close()


def test_set_and_get_state():
    repo = _repo_in_memory()
    repo.set_state("last_run", "2026-01-01")
    assert repo.get_state("last_run") == "2026-01-01"
    repo.close()


def test_get_state_default_when_missing():
    repo = _repo_in_memory()
    assert repo.get_state("nonexistent", "fallback") == "fallback"
    repo.close()


def test_set_state_upserts():
    repo = _repo_in_memory()
    repo.set_state("key", "v1")
    repo.set_state("key", "v2")
    assert repo.get_state("key") == "v2"
    repo.close()


def test_log_audit_returns_id():
    repo = _repo_in_memory()
    row_id = repo.log_audit("bot_start")
    assert row_id == 1
    repo.close()


def test_log_audit_stores_details_json():
    repo = _repo_in_memory()
    details = {"mode": "dry_run", "pairs": ["BTC/USDT"]}
    repo.log_audit("bot_start", details)
    with repo._lock:
        cur = repo._conn.cursor()
        cur.execute("SELECT details_json FROM audit_log WHERE id = 1")
        row = cur.fetchone()
    stored = json.loads(row[0])
    assert stored == details
    repo.close()


def test_close_and_reopen_preserves_data():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_file = str(Path(tmpdir) / "test.db")
        repo = SqliteSignalRepository(db_path=db_file)
        repo.save_signal(_make_signal())
        repo.set_state("k", "v")
        repo.log_audit("event")
        repo.close()

        repo2 = SqliteSignalRepository(db_path=db_file)
        assert len(repo2.get_recent_signals()) == 1
        assert repo2.get_state("k") == "v"
        repo2.close()


def test_thread_safety_concurrent_writes():
    db_file = str(Path(tempfile.gettempdir()) / f"thread_test_{threading.get_ident()}.db")
    repo = SqliteSignalRepository(db_path=db_file)
    errors: list[Exception] = []

    def write_signals(count: int) -> None:
        try:
            for i in range(count):
                repo.save_signal(_make_signal(confidence=i))
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=write_signals, args=(50,)) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert len(repo.get_recent_signals(limit=300)) == 200
    repo.close()
    Path(db_file).unlink(missing_ok=True)
