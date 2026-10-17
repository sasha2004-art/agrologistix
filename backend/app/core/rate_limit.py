"""In-memory throttling of failed PIN attempts (single-process Uvicorn).

A six-digit PIN is a small search space, so ``/auth/verify-pin`` must not accept
unlimited guesses. The backend runs as one Uvicorn process with SQLite, so a
sliding window in memory is enough; a restart clears the counters, and Nginx
``limit_req`` is the second line of defence in production.
"""

import threading
import time
from collections import deque

from fastapi import Request

from app.core.config import Settings

# Upper bound for tracked clients: keeps a hostile source from growing memory.
MAX_TRACKED_KEYS = 4096
# Local addresses of a reverse proxy whose X-Forwarded-For may be trusted.
TRUSTED_PROXY_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


def client_key(request: Request) -> str:
    """Throttling key: the real client address behind the local Nginx proxy."""

    peer = request.client.host if request.client is not None else "unknown"
    if peer in TRUSTED_PROXY_HOSTS:
        forwarded = request.headers.get("X-Forwarded-For", "")
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return peer


class LoginRateLimiter:
    """Sliding window of failed attempts plus a temporary block per client."""

    def __init__(self) -> None:
        self._failures: dict[str, deque[float]] = {}
        self._blocked_until: dict[str, float] = {}
        self._lock = threading.Lock()

    def retry_after(self, key: str, settings: Settings) -> float:
        """Seconds left of the block, or ``0.0`` when the client may try again."""

        with self._lock:
            now = time.monotonic()
            blocked_until = self._blocked_until.get(key, 0.0)
            if blocked_until <= now:
                self._blocked_until.pop(key, None)
                return 0.0
            return blocked_until - now

    def register_failure(self, key: str, settings: Settings) -> None:
        """Remember a failed PIN check and block the client after too many."""

        with self._lock:
            now = time.monotonic()
            window = max(settings.auth_rate_limit_window_sec, 1.0)
            if len(self._failures) >= MAX_TRACKED_KEYS:
                self._prune(now, window)
            attempts = self._failures.setdefault(key, deque())
            attempts.append(now)
            while attempts and now - attempts[0] > window:
                attempts.popleft()
            if len(attempts) >= settings.auth_rate_limit_max_attempts:
                self._blocked_until[key] = now + settings.auth_rate_limit_block_sec
                attempts.clear()

    def reset(self, key: str) -> None:
        """Successful login clears the failure history of the client."""

        with self._lock:
            self._failures.pop(key, None)
            self._blocked_until.pop(key, None)

    def clear(self) -> None:
        """Drop every counter; used by tests and the demo reset."""

        with self._lock:
            self._failures.clear()
            self._blocked_until.clear()

    def _prune(self, now: float, window: float) -> None:
        stale = [
            key
            for key, attempts in self._failures.items()
            if not attempts or now - attempts[-1] > window
        ]
        for key in stale:
            self._failures.pop(key, None)


LIMITER = LoginRateLimiter()
