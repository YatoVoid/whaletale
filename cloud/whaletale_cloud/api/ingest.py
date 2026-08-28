from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from schemas.wire import WIRE_SCHEMA_VERSION, IngestRequest, IngestResponse
from whaletale_cloud import models as m
from whaletale_cloud.api.deps import AuthedBox, SessionDep, require_matching_site

log = logging.getLogger("whaletale.api.ingest")
router = APIRouter()


@router.post("/v1/ingest", response_model=IngestResponse)
def ingest(
    payload: IngestRequest,
    box: AuthedBox,
    session: SessionDep,
    request: Request,
) -> IngestResponse:
    require_matching_site(box, payload.site_id, request)
    if payload.schema_version > WIRE_SCHEMA_VERSION:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"payload schema {payload.schema_version} is newer than this API "
            f"({WIRE_SCHEMA_VERSION}); upgrade the cloud",
        )
    # older versions would be upgraded here; only v1 exists so far (spec 5.3).

    obs_count = _upsert_observations(session, box.site_id, payload)
    total_count = _upsert_site_totals(session, box.site_id, payload)
    return IngestResponse(observations_upserted=obs_count, site_totals_upserted=total_count)


def _upsert_observations(session: SessionDep, site_id: object, payload: IngestRequest) -> int:
    if not payload.observations:
        return 0
    valid = {
        str(zid)
        for zid in session.scalars(
            select(m.ZoneVersion.id)
            .join(m.Space, m.Space.id == m.ZoneVersion.space_id)
            .where(m.Space.site_id == site_id)
        )
    }
    incoming = {o.zone_version_id for o in payload.observations}
    unknown = incoming - valid
    if unknown:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"zone_version_id(s) not at this site: {sorted(unknown)[:5]}",
        )

    rows = [
        {
            "zone_version_id": o.zone_version_id,
            "bucket_start": o.bucket_start,
            "bucket_end": o.bucket_end,
            "entries": o.entries,
            "exits": o.exits,
            "peak_occupancy": o.peak_occupancy,
            "occupied_seconds": o.occupied_seconds,
            "dwell_p50_seconds": o.dwell_p50_seconds,
            "dwell_p90_seconds": o.dwell_p90_seconds,
            "passersby": o.passersby,
            "capture_events": o.capture_events,
        }
        for o in payload.observations
    ]
    base = insert(m.Observation).values(rows)
    updatable = [c for c in rows[0] if c not in ("zone_version_id", "bucket_start")]
    stmt = base.on_conflict_do_update(
        index_elements=["zone_version_id", "bucket_start"],
        set_={c: getattr(base.excluded, c) for c in updatable},
    )
    session.execute(stmt)
    return len(rows)


def _upsert_site_totals(session: SessionDep, site_id: object, payload: IngestRequest) -> int:
    if not payload.site_totals:
        return 0
    if any(s.site_id != payload.site_id for s in payload.site_totals):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "site_totals carry a foreign site_id"
        )
    rows = [
        {
            "site_id": str(site_id),
            "bucket_start": s.bucket_start,
            "total_people": s.total_people,
            "active_cameras": s.active_cameras,
        }
        for s in payload.site_totals
    ]
    base = insert(m.SiteTotal).values(rows)
    stmt = base.on_conflict_do_update(
        index_elements=["site_id", "bucket_start"],
        set_={
            "total_people": base.excluded.total_people,
            "active_cameras": base.excluded.active_cameras,
        },
    )
    session.execute(stmt)
    return len(rows)
