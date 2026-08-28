"""Section 6.5 normalization: never report a raw count on its own.

Every figure carries three comparisons:
  1. share of site  - MetricSet.traffic_share
  2. against itself - same weekday and clock hours, trailing N weeks, with
     `exclude_from_baseline` days dropped
  3. against peer zones - capture rate ranked among spaces of the same kind

Anomalies (> `anomaly_sigma` SD from the trailing mean) are flagged, never
silently excluded (spec 6.5).
"""

from __future__ import annotations

import statistics
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from schemas.enums import SpaceKind
from whaletale_cloud import models as m
from whaletale_cloud.config import settings
from whaletale_cloud.metrics import MetricSet, space_metrics


@dataclass(frozen=True)
class SelfComparison:
    metric: str
    value: float
    baseline_mean: float
    baseline_stdev: float
    baseline_n: int
    z_score: float | None
    is_anomaly: bool


@dataclass(frozen=True)
class PeerRank:
    kind: SpaceKind
    capture_rate: float
    rank: int  # 1 = best capture rate among peers
    peer_count: int
    percentile: float  # 0..1, higher is better


@dataclass(frozen=True)
class NormalizedReport:
    space_id: UUID
    period: tuple[datetime, datetime]
    metrics: MetricSet
    share_of_site: float | None
    entries_vs_self: SelfComparison
    capture_rate_vs_self: SelfComparison
    peer_rank: PeerRank | None


def normalize_space(
    session: Session,
    space_id: UUID,
    start: datetime,
    end: datetime,
    *,
    baseline_weeks: int | None = None,
    anomaly_sigma: float | None = None,
) -> NormalizedReport:
    weeks = baseline_weeks if baseline_weeks is not None else settings.baseline_weeks
    sigma = anomaly_sigma if anomaly_sigma is not None else settings.anomaly_sigma

    space = session.get(m.Space, space_id)
    if space is None:
        raise LookupError(f"no space {space_id}")
    site = session.get(m.Site, space.site_id)
    assert site is not None
    tz = ZoneInfo(site.timezone)

    metrics = space_metrics(session, space_id, start, end)
    excluded = _excluded_local_dates(session, site.id, tz)

    baseline_periods = [_shift_wall_clock(start, end, tz, w) for w in range(1, weeks + 1)]
    baseline_metrics = [
        bm
        for bstart, bend in baseline_periods
        if bstart.astimezone(tz).date() not in excluded
        and (bm := space_metrics(session, space_id, bstart, bend)).bucket_count
    ]

    entries_cmp = _compare(
        "entries",
        float(metrics.entries),
        [float(bm.entries) for bm in baseline_metrics],
        sigma,
    )
    capture_cmp = _compare(
        "capture_rate",
        metrics.capture_rate,
        [bm.capture_rate for bm in baseline_metrics],
        sigma,
    )
    peer = _peer_rank(session, space, start, end, metrics.capture_rate)

    return NormalizedReport(
        space_id=space_id,
        period=(start, end),
        metrics=metrics,
        share_of_site=metrics.traffic_share,
        entries_vs_self=entries_cmp,
        capture_rate_vs_self=capture_cmp,
        peer_rank=peer,
    )


@dataclass(frozen=True)
class DailyAnomaly:
    day: date
    entries: SelfComparison
    capture_rate: SelfComparison


def iter_daily_anomalies(
    session: Session,
    space_id: UUID,
    start: datetime,
    end: datetime,
    *,
    baseline_weeks: int | None = None,
    anomaly_sigma: float | None = None,
) -> Iterator[DailyAnomaly]:
    """One `normalize_space` per local day in the period; yields only the days
    where entries or capture rate is an anomaly (spec 6.5)."""
    space = session.get(m.Space, space_id)
    if space is None:
        raise LookupError(f"no space {space_id}")
    site = session.get(m.Site, space.site_id)
    assert site is not None
    tz = ZoneInfo(site.timezone)

    day = start.astimezone(tz).date()
    last = end.astimezone(tz).date()
    while day < last:
        d0 = datetime.combine(day, time(0), tzinfo=tz).astimezone(UTC)
        d1 = datetime.combine(day + timedelta(days=1), time(0), tzinfo=tz).astimezone(UTC)
        rep = normalize_space(
            session,
            space_id,
            d0,
            d1,
            baseline_weeks=baseline_weeks,
            anomaly_sigma=anomaly_sigma,
        )
        if rep.entries_vs_self.is_anomaly or rep.capture_rate_vs_self.is_anomaly:
            yield DailyAnomaly(day, rep.entries_vs_self, rep.capture_rate_vs_self)
        day += timedelta(days=1)


def _compare(metric: str, value: float, baseline: list[float], sigma: float) -> SelfComparison:
    n = len(baseline)
    mean = statistics.fmean(baseline) if n else 0.0
    stdev = statistics.pstdev(baseline) if n >= 2 else 0.0
    z: float | None = (value - mean) / stdev if stdev > 0 else None
    return SelfComparison(
        metric=metric,
        value=value,
        baseline_mean=round(mean, 4),
        baseline_stdev=round(stdev, 4),
        baseline_n=n,
        z_score=round(z, 3) if z is not None else None,
        is_anomaly=z is not None and abs(z) > sigma,
    )


def _peer_rank(
    session: Session,
    space: m.Space,
    start: datetime,
    end: datetime,
    capture_rate: float,
) -> PeerRank | None:
    peers = list(
        session.scalars(
            select(m.Space).where(
                m.Space.site_id == space.site_id,
                m.Space.kind == space.kind,
                m.Space.archived_at.is_(None),
            )
        )
    )
    rates: list[tuple[UUID, float]] = []
    for p in peers:
        pm = space_metrics(session, p.id, start, end)
        if pm.bucket_count:
            rates.append((p.id, pm.capture_rate))
    if not any(pid == space.id for pid, _ in rates):
        return None

    rates.sort(key=lambda t: t[1], reverse=True)
    order = [pid for pid, _ in rates]
    rank = order.index(space.id) + 1
    peer_count = len(order)
    percentile = 1.0 if peer_count == 1 else (peer_count - rank) / (peer_count - 1)
    return PeerRank(
        kind=space.kind,
        capture_rate=round(capture_rate, 4),
        rank=rank,
        peer_count=peer_count,
        percentile=round(percentile, 3),
    )


def _shift_wall_clock(
    start: datetime, end: datetime, tz: ZoneInfo, weeks: int
) -> tuple[datetime, datetime]:
    """Same wall-clock time, `weeks` earlier in the site timezone, back to UTC.
    Shifting in local time (not by absolute seconds) keeps '10am Saturday'
    aligned across a DST boundary (spec 5.2.5)."""
    delta = timedelta(weeks=weeks)

    def back(dt: datetime) -> datetime:
        local = dt.astimezone(tz).replace(tzinfo=None) - delta
        return local.replace(tzinfo=tz).astimezone(UTC)

    return back(start), back(end)


def _excluded_local_dates(session: Session, site_id: UUID, tz: ZoneInfo) -> set[object]:
    rows = session.scalars(
        select(m.DayAnnotation.day).where(
            m.DayAnnotation.site_id == site_id,
            m.DayAnnotation.exclude_from_baseline.is_(True),
        )
    )
    return set(rows)
