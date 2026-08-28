from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from whaletale_cloud import models as m
from whaletale_cloud.api.security import RateLimiter, hash_token
from whaletale_cloud.db import SessionLocal

log = logging.getLogger("whaletale.api.security")

# One limiter per process. Overridable in tests via app.state.
rate_limiter = RateLimiter()


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
    if not authorization or not authorization.lower().startswith("bearer "):
        log.warning("ingest auth: missing bearer token from %s", _client_ip(request))
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    box = session.scalar(
        select(m.EdgeBox).where(
            m.EdgeBox.token_hash == hash_token(token),
            m.EdgeBox.revoked_at.is_(None),
        )
    )
    if box is None:
        log.warning("ingest auth: unknown or revoked token from %s", _client_ip(request))
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token")

    limiter: RateLimiter = getattr(request.app.state, "rate_limiter", rate_limiter)
    if not limiter.allow(box.token_hash):
        log.warning("ingest rate limit hit for box %s", box.id)
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "rate limit exceeded")

    box.last_seen_at = datetime.now(UTC)
    return box


AuthedBox = Annotated[m.EdgeBox, Depends(authenticate)]


def require_matching_site(box: m.EdgeBox, payload_site_id: str, request: Request) -> None:
    if str(box.site_id) != payload_site_id:
        log.warning(
            "site mismatch: box %s (site %s) sent payload for site %s from %s",
            box.id,
            box.site_id,
            payload_site_id,
            _client_ip(request),
        )
        raise HTTPException(status.HTTP_403_FORBIDDEN, "payload site_id does not match token")
