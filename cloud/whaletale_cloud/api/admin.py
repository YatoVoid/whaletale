"""The internal fleet admin API (spec 9). Staff-only, not per-site scoped -
a single `WHALETALE_ADMIN_TOKEN`. The customer never sees this.
"""

from __future__ import annotations

import hmac
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import select

from whaletale_cloud import models as m
from whaletale_cloud.api.deps import SessionDep, get_login_throttle
from whaletale_cloud.api.security import security_event
from whaletale_cloud.config import settings
from whaletale_cloud.fleet import evaluate_fleet, sync_alerts

router = APIRouter(prefix="/admin")


def admin_auth(request: Request, authorization: Annotated[str | None, Header()] = None) -> None:
    ip = request.client.host if request.client else "unknown"
    throttle = get_login_throttle(request)
    if not throttle.allowed(ip):
        security_event("admin_auth_locked_out", ip=ip)
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many failed attempts")

    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    if not settings.admin_token or not hmac.compare_digest(token, settings.admin_token):
        throttle.record_failure(ip)
        security_event("admin_auth_denied", ip=ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "admin auth required")
    throttle.record_success(ip)


AdminAuth = Depends(admin_auth)


class BoxHealthOut(BaseModel):
    box_id: UUID
    name: str | None
    agent_version: str | None
    last_seen_at: datetime | None
    disk_free_fraction: float | None
    buckets_pending_sync: int | None
    online: bool


class AlertOut(BaseModel):
    kind: str
    severity: str
    audience: str
    subject: str
    message: str
    edge_box_id: UUID | None


class SiteHealthOut(BaseModel):
    site_id: UUID
    site_name: str
    state: str
    boxes: list[BoxHealthOut]
    alerts: list[AlertOut]


@router.get("/fleet", response_model=list[SiteHealthOut], dependencies=[AdminAuth])
def fleet(session: SessionDep) -> list[SiteHealthOut]:
    return [
        SiteHealthOut(
            site_id=sh.site_id,
            site_name=sh.site_name,
            state=sh.state,
            boxes=[BoxHealthOut(**vars(b)) for b in sh.boxes],
            alerts=[
                AlertOut(
                    kind=a.kind,
                    severity=a.severity,
                    audience=a.audience,
                    subject=a.subject,
                    message=a.message,
                    edge_box_id=a.edge_box_id,
                )
                for a in sh.alerts
            ],
        )
        for sh in evaluate_fleet(session)
    ]


@router.post("/fleet/evaluate", dependencies=[AdminAuth])
def run_evaluation(session: SessionDep) -> dict[str, int]:
    evaluated = evaluate_fleet(session)
    opened = sync_alerts(session, evaluated)
    total = sum(len(sh.alerts) for sh in evaluated)
    security_event("admin_fleet_evaluate", sites=len(evaluated), alerts_opened=opened)
    return {"sites": len(evaluated), "alerts_active": total, "alerts_opened": opened}


class StoredAlertOut(BaseModel):
    id: UUID
    site_id: UUID
    edge_box_id: UUID | None
    kind: str
    severity: str
    audience: str
    subject: str
    message: str
    opened_at: datetime
    resolved_at: datetime | None


@router.get("/alerts", response_model=list[StoredAlertOut], dependencies=[AdminAuth])
def alerts(
    session: SessionDep,
    audience: Annotated[str | None, Query()] = None,
    include_resolved: Annotated[bool, Query()] = False,
) -> list[m.Alert]:
    stmt = select(m.Alert).order_by(m.Alert.opened_at.desc())
    if audience:
        stmt = stmt.where(m.Alert.audience == audience)
    if not include_resolved:
        stmt = stmt.where(m.Alert.resolved_at.is_(None))
    return list(session.scalars(stmt))
