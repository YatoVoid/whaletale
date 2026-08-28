"""Operator console auth.

Real login is Auth.js on the Next.js side (spec 12: do not build auth). Until
that is wired in, the API accepts a hashed bearer token per user. Whatever the
mechanism, every operator query is scoped to `ctx.site_ids` - a user only ever
sees their own sites.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select

from whaletale_cloud import models as m
from whaletale_cloud.api.deps import SessionDep, get_login_throttle
from whaletale_cloud.api.security import hash_token, new_pairing_token, security_event


@dataclass(frozen=True)
class OperatorContext:
    user: m.OperatorUser
    site_ids: frozenset[str]

    def require_site(self, site_id: str | UUID) -> str:
        sid = str(site_id)
        if sid not in self.site_ids:
            security_event("operator_site_denied", user_id=self.user.id, site_id=sid)
            raise HTTPException(status.HTTP_403_FORBIDDEN, "not your site")
        return sid


def create_operator_user(
    session: SessionDep,
    email: str,
    site_ids: list[UUID],
    name: str | None = None,
) -> tuple[m.OperatorUser, str]:
    raw = new_pairing_token()
    user = m.OperatorUser(email=email, name=name, token_hash=hash_token(raw))
    session.add(user)
    session.flush()
    session.add_all(m.OperatorUserSite(user_id=user.id, site_id=sid) for sid in site_ids)
    session.flush()
    return user, raw


def operator(
    request: Request,
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
) -> OperatorContext:
    ip = request.client.host if request.client else "unknown"
    throttle = get_login_throttle(request)
    if not throttle.allowed(ip):
        security_event("operator_auth_locked_out", ip=ip)
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many failed attempts")

    if not authorization or not authorization.lower().startswith("bearer "):
        throttle.record_failure(ip)
        security_event("operator_auth_missing_token", ip=ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    user = session.scalar(
        select(m.OperatorUser).where(
            m.OperatorUser.token_hash == hash_token(token),
            m.OperatorUser.disabled_at.is_(None),
        )
    )
    if user is None:
        throttle.record_failure(ip)
        security_event("operator_auth_invalid_token", ip=ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token")
    throttle.record_success(ip)

    site_ids = frozenset(
        str(s)
        for s in session.scalars(
            select(m.OperatorUserSite.site_id).where(m.OperatorUserSite.user_id == user.id)
        )
    )
    return OperatorContext(user=user, site_ids=site_ids)


OperatorDep = Annotated[OperatorContext, Depends(operator)]
