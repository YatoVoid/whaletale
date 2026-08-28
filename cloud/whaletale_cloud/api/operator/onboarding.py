"""Camera and edge-box onboarding (spec 7, operator side).

The validation gate runs on the edge box (`whaletale-onboard`) — only the box
can actually open the stream and time a test inference. These endpoints record
the result: pair a box, and register a camera the box has validated.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from schemas.enums import CameraStatus
from whaletale_cloud import models as m
from whaletale_cloud.api.deps import SessionDep
from whaletale_cloud.api.operator.auth import OperatorDep
from whaletale_cloud.api.operator.schemas import (
    CameraIn,
    CameraOut,
    EdgeBoxOut,
    PairEdgeBoxIn,
    PairEdgeBoxOut,
)
from whaletale_cloud.api.pairing import pair_edge_box

router = APIRouter(prefix="/v1")


@router.get("/sites/{site_id}/cameras", response_model=list[CameraOut])
def list_cameras(session: SessionDep, ctx: OperatorDep, site_id: UUID) -> list[m.Camera]:
    ctx.require_site(site_id)
    return list(session.scalars(select(m.Camera).where(m.Camera.site_id == site_id)))


@router.post("/sites/{site_id}/cameras", response_model=CameraOut, status_code=201)
def register_camera(
    session: SessionDep, ctx: OperatorDep, site_id: UUID, body: CameraIn
) -> m.Camera:
    ctx.require_site(site_id)
    from whaletale_cloud.billing import get_subscription, is_read_only

    if is_read_only(get_subscription(session, site_id)):
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, "billing past due; read-only")
    cam = m.Camera(
        site_id=site_id,
        name=body.name,
        resolution=body.resolution,
        fps_target=body.fps_target,
        rtsp_url_encrypted=body.rtsp_url_encrypted,
        credentials_ref=body.credentials_ref,
        status=CameraStatus.ONLINE,
    )
    session.add(cam)
    session.flush()
    return cam


@router.get("/sites/{site_id}/edge-boxes", response_model=list[EdgeBoxOut])
def list_edge_boxes(session: SessionDep, ctx: OperatorDep, site_id: UUID) -> list[m.EdgeBox]:
    ctx.require_site(site_id)
    return list(
        session.scalars(
            select(m.EdgeBox).where(m.EdgeBox.site_id == site_id, m.EdgeBox.revoked_at.is_(None))
        )
    )


@router.post("/sites/{site_id}/edge-boxes", response_model=PairEdgeBoxOut, status_code=201)
def pair_box(
    session: SessionDep, ctx: OperatorDep, site_id: UUID, body: PairEdgeBoxIn
) -> PairEdgeBoxOut:
    ctx.require_site(site_id)
    box, token = pair_edge_box(session, site_id, body.name)
    return PairEdgeBoxOut(id=box.id, pairing_token=token)


@router.post("/edge-boxes/{box_id}/revoke", status_code=204)
def revoke_box(session: SessionDep, ctx: OperatorDep, box_id: UUID) -> None:
    from datetime import UTC, datetime

    box = session.get(m.EdgeBox, box_id)
    if box is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "edge box not found")
    ctx.require_site(box.site_id)
    box.revoked_at = datetime.now(UTC)
