"""Pairing-token auth and a small in-process rate limiter for the ingest API.

Tokens are never stored raw - only their SHA-256. A single API instance holds
the rate-limit state; a horizontally-scaled deployment moves it to Redis
(spec 12).
"""

from __future__ import annotations

import hashlib
import secrets
import time
from collections import defaultdict, deque


def new_pairing_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


class RateLimiter:
    """Fixed-window-ish sliding limiter: at most `limit` hits per `window`
    seconds per key."""

    def __init__(self, limit: int = 120, window: float = 60.0) -> None:
        self.limit = limit
        self.window = window
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, *, now: float | None = None) -> bool:
        t = now if now is not None else time.monotonic()
        q = self._hits[key]
        cutoff = t - self.window
        while q and q[0] < cutoff:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(t)
        return True

    def reset(self) -> None:
        self._hits.clear()
