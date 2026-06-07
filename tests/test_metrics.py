import pytest

from core.metrics import (
    API_LATENCY_SECONDS,
    BOT_INFO,
    CIRCUIT_BREAKER_ACTIVE,
    DRAWDOWN_PCT,
    SIGNALS_TOTAL,
    get_metrics,
)


@pytest.fixture(autouse=True)
def _reset_metrics():
    """Prometheus-Collectors zwischen Tests zuruecksetzen."""
    # prometheus_client bietet kein offizielles Reset;
    # wir nutzen einen Test-spezifischen Ansatz ueber _value.get().
    yield


def test_signals_total_counter_increments():
    before = SIGNALS_TOTAL.labels(pair="BTC/USDT", action="buy")._value.get()
    SIGNALS_TOTAL.labels(pair="BTC/USDT", action="buy").inc()
    after = SIGNALS_TOTAL.labels(pair="BTC/USDT", action="buy")._value.get()
    assert after == before + 1


def test_api_latency_observation():
    API_LATENCY_SECONDS.labels(endpoint="bitget").observe(0.3)
    API_LATENCY_SECONDS.labels(endpoint="bitget").observe(0.7)
    data = get_metrics().decode()
    assert "bot_api_latency_seconds_count" in data
    assert "bot_api_latency_seconds_bucket" in data


def test_drawdown_gauge_set():
    DRAWDOWN_PCT.set(5.7)
    assert DRAWDOWN_PCT._value.get() == 5.7
    DRAWDOWN_PCT.set(0.0)


def test_circuit_breaker_default_zero():
    assert CIRCUIT_BREAKER_ACTIVE._value.get() == 0


def test_get_metrics_returns_bytes():
    result = get_metrics()
    assert isinstance(result, bytes)
    assert len(result) > 0


def test_bot_info_labels():
    BOT_INFO.labels(mode="dry_run", version="1.0").set(1)
    data = get_metrics().decode()
    assert 'bot_info{mode="dry_run",version="1.0"}' in data
