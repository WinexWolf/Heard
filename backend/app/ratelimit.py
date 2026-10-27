import math, time
from collections import defaultdict, deque


class RateLimiter:
    """In-memory sliding window: at most `limit` hits per `window` seconds per key (client IP)."""
    def __init__(self, limit: int, window: float = 3600.0, clock=time.time):
        self.limit, self.window, self.clock = limit, window, clock
        self.hits: dict[str, deque] = defaultdict(deque)

    def check(self, key: str) -> tuple[bool, int]:
        """Record a hit if allowed. Returns (allowed, retry_after_seconds)."""
        now = self.clock(); q = self.hits[key]
        while q and now - q[0] >= self.window: q.popleft()
        if len(q) >= self.limit:
            return False, max(1, math.ceil(self.window - (now - q[0])))
        q.append(now); return True, 0
