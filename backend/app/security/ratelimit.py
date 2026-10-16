import time
from collections import defaultdict, deque
from threading import Lock


class RateLimiter:
    """Per-process sliding window. Use a shared store (Redis) or the API gateway when running several workers."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str, limit: int, window_s: int) -> bool:
        if not self.enabled:
            return True
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > window_s:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            return True
