import threading
import time

import pytest

from adapters.rate_limiter import TokenBucketRateLimiter


def test_acquire_decrements_tokens():
    limiter = TokenBucketRateLimiter(rate=10.0, burst=5)
    assert limiter.available_tokens == 5.0
    assert limiter.acquire(tokens=2)
    assert limiter.available_tokens == pytest.approx(3.0, abs=0.05)


def test_acquire_refills_over_time():
    limiter = TokenBucketRateLimiter(rate=100.0, burst=10)
    limiter.acquire(tokens=10)
    assert limiter.available_tokens == pytest.approx(0.0, abs=0.05)
    time.sleep(0.05)
    assert limiter.available_tokens > 0


def test_acquire_blocks_when_empty_then_proceeds_after_refill():
    limiter = TokenBucketRateLimiter(rate=1000.0, burst=1)
    assert limiter.acquire()
    result = limiter.acquire(timeout=0.1)
    assert result is True


def test_acquire_timeout_returns_false():
    limiter = TokenBucketRateLimiter(rate=1.0, burst=1)
    assert limiter.acquire()
    result = limiter.acquire(tokens=2, timeout=0.05)
    assert result is False


def test_burst_default_equals_rate():
    limiter = TokenBucketRateLimiter(rate=10.0)
    assert limiter._burst == 10


def test_burst_custom_value():
    limiter = TokenBucketRateLimiter(rate=5.0, burst=20)
    assert limiter._burst == 20


def test_available_tokens_property():
    limiter = TokenBucketRateLimiter(rate=10.0, burst=5)
    assert limiter.available_tokens == 5.0
    limiter.acquire(tokens=3)
    assert limiter.available_tokens == pytest.approx(2.0, abs=0.05)


def test_concurrent_acquire_thread_safety():
    limiter = TokenBucketRateLimiter(rate=1000.0, burst=100)
    results: list[bool] = []
    lock = threading.Lock()

    def worker():
        local_results = []
        for _ in range(25):
            ok = limiter.acquire(timeout=2.0)
            local_results.append(ok)
        with lock:
            results.extend(local_results)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert len(results) == 100
    assert all(results)
