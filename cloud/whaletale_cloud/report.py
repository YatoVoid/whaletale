"""Assemble the Section 11 one-page report for one space over one period.

Pure data: no HTML, no PDF. `report_render` turns a `ReportData` into either.
Everything here comes from attribution + metrics + normalization, so a schedule
corrected late changes the next report (spec 5.2.1).
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from whaletale_cloud import models as m
from whaletale_cloud.attribution import AttributionRow, attribute_space
from whaletale_cloud.fleet import FleetConfig
from whaletale_cloud.metrics import aggregate, site_people_by_bucket
from whaletale_cloud.normalization import (
    PeerRank,
    SelfComparison,
    iter_daily_anomalies,
    normalize_space,
)

_WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


@dataclass(frozen=True)
class HourBar:
    hour: int  # 0..23, site-local
    entries: int


@dataclass(frozen=True)
class DayBar:
    weekday: int  # 0 = Monday
    label: str
    entries: int


@dataclass(frozen=True)
class OccupancySpan:
    occupant_name: str | None  # None == vacant
    start: date
    end: date  # inclusive


@dataclass(frozen=True)
class AnomalyRow:
    day: date
    entries_value: int
    entries_baseline_mean: float
    entries_z: float | None
    annotation_kind: str | None
    annotation_label: str | None


@dataclass(frozen=True)
class ReportData:
    site_name: str
    site_timezone: str
    space_name: str
    space_kind: str
    period_start: date  # inclusive, site-local
    period_end: date  # inclusive, site-local
    generated_at: datetime

    entries: int
    traffic_share: float | None
    capture_rate: float
    median_dwell_seconds: float
    peer_rank: PeerRank | None
    entries_vs_self: SelfComparison
    capture_rate_vs_self: SelfComparison
    degraded_bucket_count: int
    # spec 8.1: buckets a backing camera produced while its detection confidence
    # was well below its own normal (IR switch, blown highlights). Treat the
    # counts in these intervals as a floor, not a measurement.
    low_confidence_bucket_count: int

    hourly: list[HourBar]
    daily: list[DayBar]
    occupancy: list[OccupancySpan]
    anomalies: list[AnomalyRow]


def build_report(session: Session, space_id: UUID, start: datetime, end: datetime) -> ReportData:
    space = session.get(m.Space, space_id)
    if space is None:
        raise LookupError(f"no space {space_id}")
    site = session.get(m.Site, space.site_id)
    assert site is not None
    tz = ZoneInfo(site.timezone)

    rows = attribute_space(session, space_id, start, end)
    totals = site_people_by_bucket(session, site.id, start, end)
    metrics = aggregate(rows, totals)
    normalized = normalize_space(session, space_id, start, end)

    flagged = low_confidence_buckets(session, space_id, start, end)
    low_confidence_count = sum(1 for r in rows if r.bucket_start in flagged)

    period_start = start.astimezone(tz).date()
    period_end = (end.astimezone(tz) - timedelta(seconds=1)).date()
    hourly = _hourly(rows, tz)
    daily = _daily(rows, tz)
    occupancy = _occupancy_spans(rows, tz, period_start, period_end)
    anomalies = _anomalies(session, space_id, site.id, start, end, tz)

    return ReportData(
        site_name=site.name,
        site_timezone=site.timezone,
        space_name=space.name,
        space_kind=space.kind.value,
        period_start=period_start,
        period_end=period_end,
        generated_at=datetime.now(UTC),
        entries=metrics.entries,
        traffic_share=metrics.traffic_share,
        capture_rate=metrics.capture_rate,
        median_dwell_seconds=metrics.dwell_p50_seconds_est,
        peer_rank=normalized.peer_rank,
        entries_vs_self=normalized.entries_vs_self,
        capture_rate_vs_self=normalized.capture_rate_vs_self,
        degraded_bucket_count=metrics.degraded_bucket_count,
        low_confidence_bucket_count=low_confidence_count,
        hourly=hourly,
        daily=daily,
        occupancy=occupancy,
        anomalies=anomalies,
    )


_LOW_CONF_BASELINE_PAD = timedelta(days=14)  # trailing heartbeats that set "normal"
_LOW_CONF_MIN_SAMPLES = 8


def low_confidence_buckets(
    session: Session, space_id: UUID, start: datetime, end: datetime
) -> set[datetime]:
    """15-minute bucket starts where a camera backing this space was running
    well below its own baseline detection confidence (spec 8.1). Baseline is the
    75th percentile of that camera's heartbeat `mean_confidence` over the period
    plus a trailing pad, so a camera that dips every night still has a sane
    "good conditions" reference. Empty when there are no heartbeats."""
    space = session.get(m.Space, space_id)
    if space is None:
        return set()
    cam_names = {
        n
        for n in session.scalars(
            select(m.Camera.name)
            .join(m.ZoneVersion, m.ZoneVersion.camera_id == m.Camera.id)
            .where(m.ZoneVersion.space_id == space_id)
        )
    }
    if not cam_names:
        return set()

    rows = session.execute(
        select(m.Heartbeat.received_at, m.Heartbeat.per_camera).where(
            m.Heartbeat.site_id == space.site_id,
            m.Heartbeat.received_at >= start - _LOW_CONF_BASELINE_PAD,
            m.Heartbeat.received_at < end,
        )
    ).all()

    samples: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
    for received_at, per_camera in rows:
        for cam in per_camera or []:
            name = str(cam.get("id", ""))
            mc = cam.get("mean_confidence")
            if name in cam_names and isinstance(mc, int | float):
                samples[name].append((received_at, float(mc)))

    drop = FleetConfig().confidence_drop
    flagged: set[datetime] = set()
    for pts in samples.values():
        vals = sorted(v for _, v in pts)
        if len(vals) < _LOW_CONF_MIN_SAMPLES:
            continue
        baseline = vals[int(0.75 * (len(vals) - 1))]
        threshold = baseline * (1 - drop)
        by_bucket: dict[datetime, list[float]] = defaultdict(list)
        for t, v in pts:
            b = t.replace(minute=(t.minute // 15) * 15, second=0, microsecond=0)
            by_bucket[b].append(v)
        for b, vs in by_bucket.items():
            if start <= b < end and statistics.fmean(vs) < threshold:
                flagged.add(b)
    return flagged


def _hourly(rows: list[AttributionRow], tz: ZoneInfo) -> list[HourBar]:
    by_hour: Counter[int] = Counter()
    for r in rows:
        by_hour[r.bucket_start.astimezone(tz).hour] += r.entries
    return [HourBar(h, by_hour.get(h, 0)) for h in range(24)]


def _daily(rows: list[AttributionRow], tz: ZoneInfo) -> list[DayBar]:
    by_wd: Counter[int] = Counter()
    for r in rows:
        by_wd[r.bucket_start.astimezone(tz).weekday()] += r.entries
    return [DayBar(wd, _WEEKDAYS[wd], by_wd.get(wd, 0)) for wd in range(7)]


def _occupancy_spans(
    rows: list[AttributionRow], tz: ZoneInfo, period_start: date, period_end: date
) -> list[OccupancySpan]:
    """One occupant per local day - the one holding the most buckets that day -
    over every day in the period, then collapse consecutive same-occupant days
    into spans. Days with no observations (e.g. a closure) read as vacant."""
    per_day: dict[date, Counter[str | None]] = {}
    for r in rows:
        d = r.bucket_start.astimezone(tz).date()
        per_day.setdefault(d, Counter())[r.occupant_name] += 1

    spans: list[OccupancySpan] = []
    d = period_start
    while d <= period_end:
        who = per_day[d].most_common(1)[0][0] if d in per_day else None
        if spans and spans[-1].occupant_name == who:
            spans[-1] = OccupancySpan(who, spans[-1].start, d)
        else:
            spans.append(OccupancySpan(who, d, d))
        d += timedelta(days=1)
    return spans


def _anomalies(
    session: Session,
    space_id: UUID,
    site_id: UUID,
    start: datetime,
    end: datetime,
    tz: ZoneInfo,
) -> list[AnomalyRow]:
    ann = {
        a.day: a
        for a in session.scalars(
            select(m.DayAnnotation).where(
                m.DayAnnotation.site_id == site_id,
                m.DayAnnotation.day >= start.astimezone(tz).date(),
                m.DayAnnotation.day <= end.astimezone(tz).date(),
            )
        )
    }
    out: list[AnomalyRow] = []
    for da in iter_daily_anomalies(session, space_id, start, end):
        a = ann.get(da.day)
        out.append(
            AnomalyRow(
                day=da.day,
                entries_value=int(da.entries.value),
                entries_baseline_mean=da.entries.baseline_mean,
                entries_z=da.entries.z_score,
                annotation_kind=a.kind.value if a else None,
                annotation_label=a.label if a else None,
            )
        )
    return out


def demo_period(session: Session) -> tuple[UUID, datetime, datetime]:
    """The seeded demo site's last complete Mon-Sun week, for `whaletale-report`.
    Late enough that the trailing-weeks baseline (spec 6.5) is populated."""
    site = session.scalars(select(m.Site)).first()
    if site is None:
        raise LookupError("no site; run the seed first")
    tz = ZoneInfo(site.timezone)
    last_bucket = session.scalars(
        select(m.Observation.bucket_start).order_by(m.Observation.bucket_start.desc())
    ).first()
    if last_bucket is None:
        raise LookupError("no observations; run the seed first")
    last_day = last_bucket.astimezone(tz).date()
    # Monday of the last week that ends on or before the last day with data.
    end_monday = last_day - timedelta(days=last_day.weekday())
    start_monday = end_monday - timedelta(weeks=1)
    start = datetime.combine(start_monday, time(0), tzinfo=tz).astimezone(UTC)
    end = start + timedelta(weeks=1)
    space = (
        session.scalars(select(m.Space).where(m.Space.name == "Stall 3").limit(1)).first()
        or session.scalars(select(m.Space)).first()
    )
    assert space is not None
    return space.id, start, end
