"""In-memory rate limiter для защиты эндпоинтов от перебора."""

from __future__ import annotations

import threading
import time
from collections import deque


class RateLimiter:
    """Ограничивает число попыток с одного ключа (например, IP) за скользящее окно."""

    def __init__(self, max_attempts: int = 5, window_seconds: float = 60.0) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def is_allowed(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            timestamps = self._attempts.setdefault(key, deque())
            cutoff = now - self.window_seconds
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()
            if len(timestamps) >= self.max_attempts:
                return False
            timestamps.append(now)
            return True


login_rate_limiter = RateLimiter(max_attempts=5, window_seconds=60.0)


def client_ip_from_request(request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client is not None:
        return request.client.host
    return "unknown"
