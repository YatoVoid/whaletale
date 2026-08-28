from __future__ import annotations

import io
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from schemas.enums import CameraStatus
from whaletale_cloud import models as m
from whaletale_cloud.api.deps import SessionDep
from whaletale_cloud.api.operator.auth import OperatorDep
from whaletale_cloud.api.operator.schemas import (
    CurrentZoneOut,
    OccupancySpanOut,
    OccupantIn,
    OccupantOut,
    OverviewOut,
    OverviewSpaceRow,
    ReshapeIn,
    ReshapeOut,
    ScheduleCellOut,
    ScheduleGridOut,
    SiteOut,
    SpaceDetailOut,
    SpaceMetricsOut,
    SpaceOut,
    TenancyIn,
    TenancyOut,
)
from whaletale_cloud.metrics import space_metrics
from whaletale_cloud.normalization import normalize_space
from whaletale_cloud.report import build_report
from whaletale_cloud.report_render import render_pdf
from whaletale_cloud.schedule import resolve_schedule
from whaletale_cloud.validation import (
    PolygonError,
    ProposedTenancy,
    assert_saveable_polygon,
    find_tenancy_conflicts,
)

router = APIRouter(prefix="/v1")

_DEFAULT_DAYS = 7


def _require_writable(session: Session, site_id: UUID) -> None:
    """spec 8.5: after the grace window, operator writes are read-only. Ingest
    and heartbeats are never gated - that gap is unrecoverable."""
    from whaletale_cloud.billing import get_subscription, is_read_only

    if is_read_only(get_subscription(session, site_id)):
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            "billing is past due; the console is read-only until payment is resolved",
        )


def _site_or_403(
    session: Session, ctx: OperatorDep, site_id: UUID, *, writable: bool = False
) -> m.Site:
    ctx.require_site(site_id)
    site = session.get(m.Site, site_id)
    if site is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "site not found")
    if writable:
        _require_writable(session, site_id)
    return site


def _space_or_403(
    session: Session, ctx: OperatorDep, space_id: UUID, *, writable: bool = False
) -> m.Space:
    space = session.get(m.Space, space_id)
    if space is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "space not found")
    ctx.require_site(space.site_id)
    if writable:
        _require_writable(session, space.site_id)
    return space


def _period(
    tz_name: str, start: date | None, end: date | None
) -> tuple[datetime, datetime, date, date]:
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(tz_name)
    end_d = end or datetime.now(tz).date()
    start_d = start or (end_d - timedelta(days=_DEFAULT_DAYS - 1))
    s = datetime.combine(start_d, time(0), tzinfo=tz).astimezone(UTC)
    e = datetime.combine(end_d + timedelta(days=1), time(0), tzinfo=tz).astimezone(UTC)
    return s, e, start_d, end_d


def _current_occupant(session: Session, space_id: UUID, tz_name: str) -> m.Occupant | None:
    from zoneinfo import ZoneInfo

    today = datetime.now(ZoneInfo(tz_name)).date()
    grid = resolve_schedule(session, _space_site(session, space_id), today, today)
    name = grid.get((space_id, today))
    if name is None:
        return None
    return session.scalar(select(m.Occupant).where(m.Occupant.name == name).limit(1))


def _space_site(session: Session, space_id: UUID) -> UUID:
    sid = session.scalar(select(m.Space.site_id).where(m.Space.id == space_id))
    assert sid is not None
    return sid


# --- sites / spaces -------------------------------------------------------


@router.get("/sites", response_model=list[SiteOut])
def list_sites(session: SessionDep, ctx: OperatorDep) -> list[m.Site]:
    return list(
        session.scalars(select(m.Site).where(m.Site.id.in_([UUID(s) for s in ctx.site_ids])))
    )


@router.get("/sites/{site_id}/spaces", response_model=list[SpaceOut])
def list_spaces(session: SessionDep, ctx: OperatorDep, site_id: UUID) -> list[SpaceOut]:
    site = _site_or_403(session, ctx, site_id)
    today = datetime.now(_tz(site)).date()
    grid = resolve_schedule(session, site_id, today, today)
    names = {
        o.name: o.id
        for o in session.scalars(select(m.Occupant).where(m.Occupant.site_id == site_id))
    }
    out: list[SpaceOut] = []
    for sp in session.scalars(select(m.Space).where(m.Space.site_id == site_id)):
        occ_name = grid.get((sp.id, today))
        out.append(
            SpaceOut(
                id=sp.id,
                name=sp.name,
                kind=sp.kind.value,
                parent_space_id=sp.parent_space_id,
                archived=sp.archived_at is not None,
                current_occupant=occ_name,
                current_occupant_id=names.get(occ_name) if occ_name else None,
            )
        )
    return out


@router.get("/spaces/{space_id}", response_model=SpaceDetailOut)
def space_detail(
    session: SessionDep,
    ctx: OperatorDep,
    space_id: UUID,
    start: date | None = Query(None),
    end: date | None = Query(None),
) -> SpaceDetailOut:
    space = _space_or_403(session, ctx, space_id)
    site = session.get(m.Site, space.site_id)
    assert site is not None
    s, e, sd, ed = _period(site.timezone, start, end)

    rep = build_report(session, space_id, s, e)
    norm = normalize_space(session, space_id, s, e)
    occ = _current_occupant(session, space_id, site.timezone)

    return SpaceDetailOut(
        space=SpaceOut(
            id=space.id,
            name=space.name,
            kind=space.kind.value,
            parent_space_id=space.parent_space_id,
            archived=space.archived_at is not None,
            current_occupant=occ.name if occ else None,
            current_occupant_id=occ.id if occ else None,
        ),
        metrics=SpaceMetricsOut(
            period_start=sd,
            period_end=ed,
            entries=rep.entries,
            traffic_share=rep.traffic_share,
            capture_rate=rep.capture_rate,
            median_dwell_seconds=rep.median_dwell_seconds,
            peer_rank=norm.peer_rank.rank if norm.peer_rank else None,
            peer_count=norm.peer_rank.peer_count if norm.peer_rank else None,
            entries_is_anomaly=norm.entries_vs_self.is_anomaly,
            degraded_bucket_count=rep.degraded_bucket_count,
        ),
        occupancy=[
            OccupancySpanOut(occupant_name=o.occupant_name, start=o.start, end=o.end)
            for o in rep.occupancy
        ],
    )


@router.get("/spaces/{space_id}/report.pdf")
def space_report_pdf(
    session: SessionDep,
    ctx: OperatorDep,
    space_id: UUID,
    start: date | None = Query(None),
    end: date | None = Query(None),
) -> StreamingResponse:
    space = _space_or_403(session, ctx, space_id)
    site = session.get(m.Site, space.site_id)
    assert site is not None
    s, e, _sd, _ed = _period(site.timezone, start, end)
    data = build_report(session, space_id, s, e)
    pdf = render_pdf(data)
    return StreamingResponse(
        io.BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{space.name}.pdf"'},
    )


# --- occupants ----------------------------------------------------------


@router.get("/sites/{site_id}/occupants", response_model=list[OccupantOut])
def list_occupants(session: SessionDep, ctx: OperatorDep, site_id: UUID) -> list[OccupantOut]:
    _site_or_403(session, ctx, site_id)
    space_names_by_occ: dict[UUID, list[str]] = {}
    for occ_id, sp_name in session.execute(
        select(m.Tenancy.occupant_id, m.Space.name)
        .join(m.Space, m.Space.id == m.Tenancy.space_id)
        .where(m.Space.site_id == site_id)
    ):
        space_names_by_occ.setdefault(occ_id, [])
        if sp_name not in space_names_by_occ[occ_id]:
            space_names_by_occ[occ_id].append(sp_name)
    return [
        OccupantOut(
            id=o.id,
            name=o.name,
            contact_email=o.contact_email,
            contact_phone=o.contact_phone,
            archived=o.archived_at is not None,
            space_names=space_names_by_occ.get(o.id, []),
        )
        for o in session.scalars(select(m.Occupant).where(m.Occupant.site_id == site_id))
    ]


@router.post("/sites/{site_id}/occupants", response_model=OccupantOut, status_code=201)
def create_occupant(
    session: SessionDep, ctx: OperatorDep, site_id: UUID, body: OccupantIn
) -> OccupantOut:
    _site_or_403(session, ctx, site_id, writable=True)
    occ = m.Occupant(
        site_id=site_id,
        name=body.name,
        contact_email=body.contact_email,
        contact_phone=body.contact_phone,
    )
    session.add(occ)
    session.flush()
    return OccupantOut(
        id=occ.id,
        name=occ.name,
        contact_email=occ.contact_email,
        contact_phone=occ.contact_phone,
        archived=False,
        space_names=[],
    )


@router.patch("/occupants/{occupant_id}", response_model=OccupantOut)
def update_occupant(
    session: SessionDep, ctx: OperatorDep, occupant_id: UUID, body: OccupantIn
) -> OccupantOut:
    occ = session.get(m.Occupant, occupant_id)
    if occ is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "occupant not found")
    ctx.require_site(occ.site_id)
    _require_writable(session, occ.site_id)
    # spec 8.3: rename in place; history is a join, so it updates everywhere.
    occ.name = body.name
    occ.contact_email = body.contact_email
    occ.contact_phone = body.contact_phone
    session.flush()
    return OccupantOut(
        id=occ.id,
        name=occ.name,
        contact_email=occ.contact_email,
        contact_phone=occ.contact_phone,
        archived=occ.archived_at is not None,
        space_names=[],
    )


# --- schedule + tenancies ---------------------------------------------


@router.get("/sites/{site_id}/schedule", response_model=ScheduleGridOut)
def schedule(
    session: SessionDep,
    ctx: OperatorDep,
    site_id: UUID,
    start: date = Query(...),
    end: date = Query(...),
) -> ScheduleGridOut:
    _site_or_403(session, ctx, site_id)
    if end < start:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "end before start")
    if (end - start).days > 62:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "range too wide (max 62 days)")

    grid = resolve_schedule(session, site_id, start, end)
    spaces = list(
        session.scalars(
            select(m.Space).where(m.Space.site_id == site_id, m.Space.archived_at.is_(None))
        )
    )
    days = sorted({d for _sid, d in grid})
    return ScheduleGridOut(
        site_id=site_id,
        days=days,
        space_ids=[sp.id for sp in spaces],
        space_names={str(sp.id): sp.name for sp in spaces},
        cells=[
            ScheduleCellOut(space_id=sid, day=d, occupant_name=name)
            for (sid, d), name in sorted(grid.items(), key=lambda kv: (str(kv[0][0]), kv[0][1]))
        ],
    )


@router.post("/spaces/{space_id}/tenancies", response_model=TenancyOut, status_code=201)
def create_tenancy(
    session: SessionDep, ctx: OperatorDep, space_id: UUID, body: TenancyIn
) -> TenancyOut:
    space = _space_or_403(session, ctx, space_id, writable=True)
    occ = session.get(m.Occupant, body.occupant_id)
    if occ is None or occ.site_id != space.site_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "occupant not at this site")

    dst = _parse_hhmm(body.daily_start_time)
    det = _parse_hhmm(body.daily_end_time)
    proposed = ProposedTenancy(
        space_id=space_id,
        kind=body.kind,
        starts_on=body.starts_on,
        ends_on=body.ends_on,
        recurrence_rule=body.recurrence_rule,
        daily_start_time=dst,
        daily_end_time=det,
    )
    conflicts = find_tenancy_conflicts(session, proposed)
    if conflicts:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {
                "detail": "overlaps an existing tenancy",
                "conflicting_tenancy_ids": [str(c.id) for c in conflicts],
            },
        )

    t = m.Tenancy(
        space_id=space_id,
        occupant_id=body.occupant_id,
        kind=body.kind,
        starts_on=body.starts_on,
        ends_on=body.ends_on,
        recurrence_rule=body.recurrence_rule,
        daily_start_time=dst,
        daily_end_time=det,
        rate_amount=body.rate_amount,
        rate_period=body.rate_period,
        notes=body.notes,
        created_at=datetime.now(UTC),
    )
    session.add(t)
    session.flush()
    return TenancyOut(
        id=t.id,
        space_id=space_id,
        occupant_id=t.occupant_id,
        occupant_name=occ.name,
        kind=t.kind.value,
        starts_on=t.starts_on,
        ends_on=t.ends_on,
        recurrence_rule=t.recurrence_rule,
    )


@router.delete("/tenancies/{tenancy_id}", status_code=204)
def delete_tenancy(session: SessionDep, ctx: OperatorDep, tenancy_id: UUID) -> None:
    t = session.get(m.Tenancy, tenancy_id)
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "tenancy not found")
    space = session.get(m.Space, t.space_id)
    assert space is not None
    ctx.require_site(space.site_id)
    _require_writable(session, space.site_id)
    session.delete(t)  # spec 8.3: retroactive edit; affected reports recompute on the join


# --- zone editor -----------------------------------------------------


@router.get(
    "/spaces/{space_id}/zone-versions/current",
    response_model=CurrentZoneOut,
)
def current_zone(session: SessionDep, ctx: OperatorDep, space_id: UUID) -> CurrentZoneOut:
    _space_or_403(session, ctx, space_id)
    versions = list(
        session.scalars(
            select(m.ZoneVersion)
            .where(m.ZoneVersion.space_id == space_id)
            .order_by(m.ZoneVersion.effective_from)
        )
    )
    idx = next(
        (i for i, v in enumerate(versions) if v.is_primary and v.effective_to is None),
        None,
    )
    if idx is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no open primary zone version")
    v = versions[idx]
    return CurrentZoneOut(
        zone_version_id=v.id,
        polygon=[(p[0], p[1]) for p in v.polygon],
        version_number=idx + 1,
    )


@router.post(
    "/spaces/{space_id}/zone-versions/reshape",
    response_model=ReshapeOut,
    status_code=201,
)
def reshape_zone(
    session: SessionDep, ctx: OperatorDep, space_id: UUID, body: ReshapeIn
) -> ReshapeOut:
    _space_or_403(session, ctx, space_id, writable=True)
    try:
        assert_saveable_polygon(body.polygon)
    except PolygonError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    versions = list(
        session.scalars(
            select(m.ZoneVersion)
            .where(m.ZoneVersion.space_id == space_id)
            .order_by(m.ZoneVersion.effective_from)
        )
    )
    open_primary = next((v for v in versions if v.is_primary and v.effective_to is None), None)
    if open_primary is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "no open primary zone version to reshape; create one via onboarding",
        )
    if body.base_version_id is not None and body.base_version_id != open_primary.id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "this zone changed since you opened it; reload and reapply your edit",
        )

    now = datetime.now(UTC)
    # spec 5.2.2: never edit geometry in place. Close the current, insert a new.
    open_primary.effective_to = now
    new = m.ZoneVersion(
        space_id=space_id,
        camera_id=open_primary.camera_id,
        polygon=[list(p) for p in body.polygon],
        is_primary=True,
        effective_from=now,
        created_by=body.created_by,
    )
    session.add(new)
    session.flush()
    version_number = len(versions) + 1
    return ReshapeOut(
        zone_version_id=new.id,
        version_number=version_number,
        previous_version_id=open_primary.id,
        message=(
            f"Reshaping creates version {version_number}. "
            f"Reports before today keep version {version_number - 1}."
        ),
    )


# --- overview -------------------------------------------------------


@router.get("/sites/{site_id}/overview", response_model=OverviewOut)
def overview(
    session: SessionDep,
    ctx: OperatorDep,
    site_id: UUID,
    start: date | None = Query(None),
    end: date | None = Query(None),
) -> OverviewOut:
    site = _site_or_403(session, ctx, site_id)
    s, e, sd, ed = _period(site.timezone, start, end)

    today = datetime.now(_tz(site)).date()
    grid = resolve_schedule(session, site_id, today, today)

    rows: list[OverviewSpaceRow] = []
    vacant: list[UUID] = []
    for sp in session.scalars(
        select(m.Space).where(m.Space.site_id == site_id, m.Space.archived_at.is_(None))
    ):
        ms = space_metrics(session, sp.id, s, e)
        occ_name = grid.get((sp.id, today))
        if occ_name is None:
            vacant.append(sp.id)
        rows.append(
            OverviewSpaceRow(
                space_id=sp.id,
                name=sp.name,
                kind=sp.kind.value,
                entries=ms.entries,
                capture_rate=ms.capture_rate,
                occupant_name=occ_name,
                is_vacant=occ_name is None,
            )
        )
    rows.sort(key=lambda r: r.capture_rate, reverse=True)

    boxes = list(session.scalars(select(m.EdgeBox).where(m.EdgeBox.site_id == site_id)))
    online_cut = datetime.now(UTC) - timedelta(hours=1)
    boxes_online = sum(
        1 for b in boxes if b.last_seen_at is not None and b.last_seen_at >= online_cut
    )
    cameras_offline = [
        c.name
        for c in session.scalars(
            select(m.Camera).where(
                m.Camera.site_id == site_id, m.Camera.status == CameraStatus.OFFLINE
            )
        )
    ]

    return OverviewOut(
        site=SiteOut(id=site.id, name=site.name, timezone=site.timezone, status=site.status.value),
        period_start=sd,
        period_end=ed,
        spaces=rows,
        vacant_space_ids=vacant,
        boxes_online=boxes_online,
        boxes_total=len(boxes),
        cameras_offline=cameras_offline,
    )


def _tz(site: m.Site) -> ZoneInfo:
    from zoneinfo import ZoneInfo

    return ZoneInfo(site.timezone)


def _parse_hhmm(v: str | None) -> time | None:
    if not v:
        return None
    hh, mm = v.split(":")
    return time(int(hh), int(mm))
