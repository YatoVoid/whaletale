"""The Section 6.4 metrics, computed over attributed buckets.

Built by hand (spec 12: "build yourself ... the metric definitions in 6.4").
Definitions are fixed here and nowhere else.

Two Section 5.1 gaps show up at this layer and are approximated, not invented:
  - `observations` has no person-seconds column, so period person-seconds is not
    derivable in the cloud. It is omitted rather than guessed.
  - dwell is stored per bucket as p50/p90; a true period percentile needs the
    per-track samples, which are not synced. Period dwell here is the
    entries-weighted mean of the bucket percentiles, labelled as an estimate.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from schemas.enums import BucketQuality
from whaletale_cloud import models as m
from whaletale_cloud.attribution import AttributionRow, attribute_space


@dataclass(frozen=True)
class MetricSet:
    bucket_count: int
    entries: int
    exits: int
    passersby: int
    capture_events: int
    peak_occupancy: int
    occupied_seconds: float
    dwell_p50_seconds_est: float
    dwell_p90_seconds_est: float
    degraded_bucket_count: int
    site_people: int | None  # sum of site_totals.total_people over the same buckets
    person_seconds: None = None  # not derivable from the 5.1 schema; see module docstring

    @property
    def capture_rate(self) -> float:
        """spec 6.4: entries / (entries + passersby). `capture_events` is the
        stored numerator; the seed sets it equal to `entries`."""
        denom = self.capture_events + self.passersby
        return self.capture_events / denom if denom else 0.0

    @property
    def traffic_share(self) -> float | None:
        """spec 6.4: zone entries / site total people, same buckets."""
        if not self.site_people:
            return None
        return self.entries / self.site_people


def aggregate(
    rows: Sequence[AttributionRow], site_people_by_bucket: Mapping[datetime, int]
) -> MetricSet:
    if not rows:
        return MetricSet(0, 0, 0, 0, 0, 0, 0.0, 0.0, 0.0, 0, None)

    entries = sum(r.entries for r in rows)
    weight = entries or len(rows)
    p50 = sum(r.dwell_p50_seconds * (r.entries or 1) for r in rows) / weight
    p90 = sum(r.dwell_p90_seconds * (r.entries or 1) for r in rows) / weight
    buckets = {r.bucket_start for r in rows}
    site_people = sum(site_people_by_bucket.get(b, 0) for b in buckets)

    return MetricSet(
        bucket_count=len(rows),
        entries=entries,
        exits=sum(r.exits for r in rows),
        passersby=sum(r.passersby for r in rows),
        capture_events=sum(r.capture_events for r in rows),
        peak_occupancy=max((r.peak_occupancy for r in rows), default=0),
        occupied_seconds=sum(r.occupied_seconds for r in rows),
        dwell_p50_seconds_est=round(p50, 1),
        dwell_p90_seconds_est=round(p90, 1),
        degraded_bucket_count=sum(1 for r in rows if r.quality is BucketQuality.DEGRADED),
        site_people=site_people or None,
    )


def site_people_by_bucket(
    session: Session, site_id: UUID, start: datetime, end: datetime
) -> dict[datetime, int]:
    rows = session.execute(
        select(m.SiteTotal.bucket_start, m.SiteTotal.total_people).where(
            m.SiteTotal.site_id == site_id,
            m.SiteTotal.bucket_start >= start,
            m.SiteTotal.bucket_start < end,
        )
    )
    return {bstart: people for bstart, people in rows}


def space_metrics(
    session: Session,
    space_id: UUID,
    start: datetime,
    end: datetime,
    *,
    occupant_id: UUID | None = None,
) -> MetricSet:
    """Period metrics for one space. With `occupant_id`, only the buckets that
    occupant held (spec 5.2.1 attribution), for a per-tenant report line."""
    space = session.get(m.Space, space_id)
    if space is None:
        raise LookupError(f"no space {space_id}")
    rows = attribute_space(session, space_id, start, end)
    if occupant_id is not None:
        rows = [r for r in rows if r.occupant_id == occupant_id]
    totals = site_people_by_bucket(session, space.site_id, start, end)
    return aggregate(rows, totals)
