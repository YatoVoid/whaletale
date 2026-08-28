"""Operator console auth.

Real login is Auth.js on the Next.js side (spec 12: do not build auth). Until
that is wired in, the API accepts a hashed bearer token per user. Whatever the
mechanism, every operator query is scoped to `ctx.site_ids` - a user only ever
sees their own sites.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select

from whaletale_cloud import models as m
from whaletale_cloud.api.deps import SessionDep
from whaletale_cloud.api.security import hash_token, new_pairing_token

log = logging.getLogger("whaletale.api.operator")


@dataclass(frozen=True)
class OperatorContext:
    user: m.OperatorUser
    site_ids: frozenset[str]

    def require_site(self, site_id: str | UUID) -> str:
        sid = str(site_id)
        if sid not in self.site_ids:
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
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    user = session.scalar(
        select(m.OperatorUser).where(
            m.OperatorUser.token_hash == hash_token(token),
            m.OperatorUser.disabled_at.is_(None),
        )
    )
    if user is None:
        ip = request.client.host if request.client else "unknown"
        log.warning("operator auth: unknown or disabled token from %s", ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token")

    site_ids = frozenset(
        str(s)
        for s in session.scalars(
            select(m.OperatorUserSite.site_id).where(m.OperatorUserSite.user_id == user.id)
        )
    )
    return OperatorContext(user=user, site_ids=site_ids)


OperatorDep = Annotated[OperatorContext, Depends(operator)]
