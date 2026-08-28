"""Pairing-token auth and a small in-process rate limiter for the ingest API.

Tokens are never stored raw - only their SHA-256. A single API instance holds
the rate-limit state; a horizontally-scaled deployment moves it to Redis
(spec 12).
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import time
from collections import defaultdict, deque

_audit = logging.getLogger("whaletale.security")


def security_event(event: str, **fields: object) -> None:
    """One structured line per auth failure, permission denial, or admin action,
    on a dedicated logger so it can be shipped somewhere queryable (spec 12 /
    vibe-check: log security events)."""
    detail = " ".join(f"{k}={v}" for k, v in fields.items())
    _audit.warning("%s %s", event, detail)


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


class LoginThrottle:
    """Per-key lockout after repeated auth failures (vibe-check: lock accounts
    after failed login, rate-limit auth). Keyed by client IP so an unknown-token
    brute force is blunted before it reaches the token lookup. A success clears
    the key. In-process like `RateLimiter`; Redis in a scaled deployment."""

    def __init__(self, max_failures: int = 10, window: float = 900.0) -> None:
        self.max_failures = max_failures
        self.window = window
        self._fails: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, key: str, t: float) -> deque[float]:
        q = self._fails[key]
        cutoff = t - self.window
        while q and q[0] < cutoff:
            q.popleft()
        return q

    def allowed(self, key: str, *, now: float | None = None) -> bool:
        t = now if now is not None else time.monotonic()
        return len(self._prune(key, t)) < self.max_failures

    def record_failure(self, key: str, *, now: float | None = None) -> None:
        t = now if now is not None else time.monotonic()
        self._prune(key, t).append(t)

    def record_success(self, key: str) -> None:
        self._fails.pop(key, None)

    def reset(self) -> None:
        self._fails.clear()
