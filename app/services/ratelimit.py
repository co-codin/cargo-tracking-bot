"""Простой in-memory token bucket (на пользователя / IP)."""
import threading, time


class TokenBucket:
    def __init__(self, rate=1.0, burst=5, max_keys=10000):
        self.rate, self.burst, self.max_keys = rate, burst, max_keys
        self._b = {}
        self._lock = threading.Lock()

    def allow(self, key, now=None):
        now = time.monotonic() if now is None else now
        with self._lock:
            tokens, t = self._b.get(key, (self.burst, now))
            tokens = min(self.burst, tokens + (now - t) * self.rate)
            ok = tokens >= 1
            if ok:
                tokens -= 1
            if len(self._b) >= self.max_keys and key not in self._b:
                self._b.clear()
            self._b[key] = (tokens, now)
            return ok


bot_limiter = TokenBucket(rate=1.0, burst=5)
api_limiter = TokenBucket(rate=5.0, burst=20)
