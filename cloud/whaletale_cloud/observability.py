"""Sentry wiring (spec 9: use Sentry for exceptions, do not build error
tracking). No-op unless `SENTRY_DSN` is set and `sentry-sdk` is installed."""

from __future__ import annotations

from whaletale_cloud import __version__
from whaletale_cloud.config import settings


def init_sentry() -> bool:
    if not settings.sentry_dsn:
        return False
    try:
        import sentry_sdk
    except ImportError:
        return False
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        release=f"whaletale-cloud@{__version__}",
        traces_sample_rate=0.0,
        send_default_pii=False,
    )
    return True
