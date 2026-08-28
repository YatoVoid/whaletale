"""Attribution: which occupant held a space during each observation bucket.

Spec 5.2.1 - the occupant is never written onto an observation. This module is
the query-time join that resolves it, so a schedule corrected weeks late fixes
all history on the next run.

Spec 5.2.2 / 6.6 - each bucket is resolved against the zone version effective at
that instant; if the primary version has no observation for a bucket, a
non-primary (failover) version is used and the bucket is marked degraded.

Spec 8.3 - a `closure` day annotation suppresses any tenancy for that local day;
the space reads as vacant, which is real information.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time
from uuid import UUID
from zoneinfo import ZoneInfo

from dateutil.rrule import rrulestr
from sqlalchemy import select
from sqlalchemy.orm import Session

from schemas.enums import BucketQuality, DayAnnotationKind, TenancyKind
from whaletale_cloud import models as m


@dataclass(frozen=True)
class AttributionRow:
    bucket_start: datetime
    bucket_end: datetime
    zone_version_id: UUID
    quality: BucketQuality
    occupant_id: UUID | None
    occupant_name: str | None
    entries: int
    exits: int
    peak_occupancy: int
    occupied_seconds: float
    dwell_p50_seconds: float
    dwell_p90_seconds: float
    passersby: int
    capture_events: int

    @property
    def is_vacant(self) -> bool:
        return self.occupant_id is None


def attribute_space(
    session: Session, space_id: UUID, start: datetime, end: datetime
) -> list[AttributionRow]:
    """Attributed observation buckets for one space over ``[start, end)``.

    Buckets with no observation on any of the space's zone versions are omitted -
    absence of data is not the same as a vacant, occupied, or zero bucket.
    """
    space = session.get(m.Space, space_id)
    if space is None:
        raise LookupError(f"no space {space_id}")
    site = session.get(m.Site, space.site_id)
    assert site is not None
    tz = ZoneInfo(site.timezone)

    zone_versions = list(
        session.scalars(select(m.ZoneVersion).where(m.ZoneVersion.space_id == space_id))
    )
    primaries = [z for z in zone_versions if z.is_primary]
    secondaries = [z for z in zone_versions if not z.is_primary]

    observations = list(
        session.scalars(
            select(m.Observation)
            .where(
                m.Observation.zone_version_id.in_([z.id for z in zone_versions]),
                m.Observation.bucket_start >= start,
                m.Observation.bucket_start < end,
            )
            .order_by(m.Observation.bucket_start)
        )
    )
    by_bucket_zv = {(o.bucket_start, o.zone_version_id): o for o in observations}
    buckets = sorted({o.bucket_start for o in observations})

    occupants = {
        o.id: o
        for o in session.scalars(
            select(m.Occupant).where(m.Occupant.site_id == site.id)
        )
    }
    tenancies = list(
        session.scalars(
            select(m.Tenancy)
            .where(m.Tenancy.space_id == space_id)
            .order_by(m.Tenancy.created_at)
        )
    )
    closures = _closure_days(session, site.id, start, end, tz)
    recurrences = _recurrence_dates(
        tenancies, start.astimezone(tz).date(), end.astimezone(tz).date()
    )

    rows: list[AttributionRow] = []
    for bucket_start in buckets:
        obs, zone_version_id, quality = _resolve_bucket(
            bucket_start, primaries, secondaries, by_bucket_zv
        )
        if obs is None or zone_version_id is None:
            continue
        occ_id = _occupant_at(bucket_start, tz, tenancies, closures, recurrences)
        occ = occupants.get(occ_id) if occ_id else None
        rows.append(
            AttributionRow(
                bucket_start=obs.bucket_start,
                bucket_end=obs.bucket_end,
                zone_version_id=zone_version_id,
                quality=quality,
                occupant_id=occ.id if occ else None,
                occupant_name=occ.name if occ else None,
                entries=obs.entries,
                exits=obs.exits,
                peak_occupancy=obs.peak_occupancy,
                occupied_seconds=obs.occupied_seconds,
                dwell_p50_seconds=obs.dwell_p50_seconds,
                dwell_p90_seconds=obs.dwell_p90_seconds,
                passersby=obs.passersby,
                capture_events=obs.capture_events,
            )
        )
    return rows


def _resolve_bucket(
    bucket_start: datetime,
    primaries: list[m.ZoneVersion],
    secondaries: list[m.ZoneVersion],
    by_bucket_zv: dict[tuple[datetime, UUID], m.Observation],
) -> tuple[m.Observation | None, UUID | None, BucketQuality]:
    primary = _effective_version(primaries, bucket_start)
    if primary is not None:
        obs = by_bucket_zv.get((bucket_start, primary.id))
        if obs is not None:
            return obs, primary.id, BucketQuality.OK
    for sec in secondaries:
        if _covers(sec, bucket_start):
            obs = by_bucket_zv.get((bucket_start, sec.id))
            if obs is not None:
                # spec 6.6: primary unavailable this bucket, secondary stood in.
                return obs, sec.id, BucketQuality.DEGRADED
    return None, None, BucketQuality.OK


def _effective_version(
    versions: Iterable[m.ZoneVersion], when: datetime
) -> m.ZoneVersion | None:
    for v in versions:
        if _covers(v, when):
            return v
    return None


def _covers(v: m.ZoneVersion, when: datetime) -> bool:
    return v.effective_from <= when and (v.effective_to is None or when < v.effective_to)


def _closure_days(
    session: Session, site_id: UUID, start: datetime, end: datetime, tz: ZoneInfo
) -> set[date]:
    rows = session.scalars(
        select(m.DayAnnotation.day).where(
            m.DayAnnotation.site_id == site_id,
            m.DayAnnotation.kind == DayAnnotationKind.CLOSURE,
            m.DayAnnotation.day >= start.astimezone(tz).date(),
            m.DayAnnotation.day <= end.astimezone(tz).date(),
        )
    )
    return set(rows)


def _recurrence_dates(
    tenancies: list[m.Tenancy], window_start: date, window_end: date
) -> dict[UUID, set[date]]:
    out: dict[UUID, set[date]] = {}
    for t in tenancies:
        if t.kind is not TenancyKind.RECURRING or not t.recurrence_rule:
            continue
        rule = rrulestr(t.recurrence_rule, dtstart=datetime.combine(t.starts_on, time()))
        lo = datetime.combine(max(window_start, t.starts_on), time())
        hi = datetime.combine(window_end, time())
        out[t.id] = {occ.date() for occ in rule.between(lo, hi, inc=True)}
    return out


def _occupant_at(
    bucket_start: datetime,
    tz: ZoneInfo,
    tenancies: list[m.Tenancy],
    closures: set[date],
    recurrences: dict[UUID, set[date]],
) -> UUID | None:
    local = bucket_start.astimezone(tz)
    local_day, local_time = local.date(), local.time()
    if local_day in closures:
        return None
    for t in tenancies:  # ordered by created_at; first match wins
        if _tenancy_active(t, local_day, local_time, recurrences):
            return t.occupant_id
    return None


def _tenancy_active(
    t: m.Tenancy, day: date, clock: time, recurrences: dict[UUID, set[date]]
) -> bool:
    if day < t.starts_on:
        return False
    if t.ends_on is not None and day > t.ends_on:
        return False
    if t.kind is TenancyKind.PERMANENT:
        return True
    if t.kind is TenancyKind.ONE_OFF:
        return day == t.starts_on
    # recurring
    if day not in recurrences.get(t.id, set()):
        return False
    if t.daily_start_time is not None and t.daily_end_time is not None:
        return t.daily_start_time <= clock < t.daily_end_time
    return True
