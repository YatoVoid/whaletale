from __future__ import annotations

from whaletale_cloud.api.security import LoginThrottle, RateLimiter


def test_rate_limiter_allows_up_to_limit_then_blocks() -> None:
    rl = RateLimiter(limit=3, window=60.0)
    assert [rl.allow("k", now=0.0) for _ in range(5)] == [True, True, True, False, False]


def test_rate_limiter_window_slides() -> None:
    rl = RateLimiter(limit=2, window=10.0)
    assert rl.allow("k", now=0.0)
    assert rl.allow("k", now=1.0)
    assert not rl.allow("k", now=2.0)
    assert rl.allow("k", now=11.5)  # first hit has aged out


def test_login_throttle_locks_out_after_max_failures() -> None:
    lt = LoginThrottle(max_failures=3, window=900.0)
    assert lt.allowed("1.2.3.4", now=0.0)
    for i in range(3):
        lt.record_failure("1.2.3.4", now=float(i))
    assert not lt.allowed("1.2.3.4", now=3.0)
    assert lt.allowed("5.6.7.8", now=3.0)  # a different client is unaffected


def test_login_throttle_success_clears_the_key() -> None:
    lt = LoginThrottle(max_failures=2, window=900.0)
    lt.record_failure("ip", now=0.0)
    lt.record_failure("ip", now=1.0)
    assert not lt.allowed("ip", now=1.0)
    lt.record_success("ip")
    assert lt.allowed("ip", now=1.0)


def test_login_throttle_failures_age_out() -> None:
    lt = LoginThrottle(max_failures=2, window=100.0)
    lt.record_failure("ip", now=0.0)
    lt.record_failure("ip", now=10.0)
    assert not lt.allowed("ip", now=10.0)
    assert lt.allowed("ip", now=101.0)  # both failures older than the window
