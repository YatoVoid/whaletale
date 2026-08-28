from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from whaletale_cloud import models as m
from whaletale_cloud.api.security import (
    LoginThrottle,
    RateLimiter,
    hash_token,
    security_event,
)
from whaletale_cloud.db import SessionLocal

# One limiter per process. Overridable in tests via app.state.
rate_limiter = RateLimiter()
login_throttle = LoginThrottle()


def get_login_throttle(request: Request) -> LoginThrottle:
    return getattr(request.app.state, "login_throttle", login_throttle)


def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


SessionDep = Annotated[Session, Depends(get_session)]


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def authenticate(
    request: Request,
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
) -> m.EdgeBox:
    ip = _client_ip(request)
    throttle = get_login_throttle(request)
    if not throttle.allowed(ip):
        security_event("ingest_auth_locked_out", ip=ip)
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many failed attempts")

    if not authorization or not authorization.lower().startswith("bearer "):
        throttle.record_failure(ip)
        security_event("ingest_auth_missing_token", ip=ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    box = session.scalar(
        select(m.EdgeBox).where(
            m.EdgeBox.token_hash == hash_token(token),
            m.EdgeBox.revoked_at.is_(None),
        )
    )
    if box is None:
        throttle.record_failure(ip)
        security_event("ingest_auth_invalid_token", ip=ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token")
    throttle.record_success(ip)

    limiter: RateLimiter = getattr(request.app.state, "rate_limiter", rate_limiter)
    if not limiter.allow(box.token_hash):
        security_event("ingest_rate_limited", box_id=box.id, ip=ip)
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "rate limit exceeded")

    box.last_seen_at = datetime.now(UTC)
    return box


AuthedBox = Annotated[m.EdgeBox, Depends(authenticate)]


def require_matching_site(box: m.EdgeBox, payload_site_id: str, request: Request) -> None:
    if str(box.site_id) != payload_site_id:
        security_event(
            "ingest_site_mismatch",
            box_id=box.id,
            token_site=box.site_id,
            payload_site=payload_site_id,
            ip=_client_ip(request),
        )
        raise HTTPException(status.HTTP_403_FORBIDDEN, "payload site_id does not match token")
