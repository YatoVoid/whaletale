from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Request

from schemas.wire import HeartbeatRequest, HeartbeatResponse
from whaletale_cloud import models as m
from whaletale_cloud.api.deps import AuthedBox, SessionDep, require_matching_site

router = APIRouter()


@router.post("/v1/heartbeat", response_model=HeartbeatResponse)
def heartbeat(
    payload: HeartbeatRequest,
    box: AuthedBox,
    session: SessionDep,
    request: Request,
) -> HeartbeatResponse:
    require_matching_site(box, payload.site_id, request)

    box.agent_version = payload.agent_version
    now = datetime.now(UTC)
    session.add(
        m.Heartbeat(
            edge_box_id=box.id,
            site_id=box.site_id,
            received_at=now,
            agent_version=payload.agent_version,
            uptime_seconds=payload.uptime_seconds,
            cpu_percent=payload.cpu_percent,
            mem_percent=payload.mem_percent,
            disk_free_bytes=payload.disk_free_bytes,
            buckets_pending_sync=payload.buckets_pending_sync,
            last_sync_at=payload.last_sync_at,
            per_camera=[c.model_dump(mode="json") for c in payload.per_camera],
        )
    )
    return HeartbeatResponse(received_at=now, agent_version_current=None)
