from __future__ import annotations

import threading
import time


class TokenBucketRateLimiter:
    """Thread-safe Token-Bucket Rate Limiter."""

    def __init__(self, rate: float, burst: int | None = None):
        self._rate = rate
        self._burst = burst if burst is not None else max(1, int(rate))
        self._tokens = float(self._burst)
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self, tokens: int = 1, timeout: float | None = None) -> bool:
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            with self._lock:
                self._refill()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return True
            if deadline is not None and time.monotonic() >= deadline:
                return False
            time.sleep(0.01)

    @property
    def available_tokens(self) -> float:
        with self._lock:
            self._refill()
            return self._tokens

    def _refill(self):
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
        self._last_refill = now
