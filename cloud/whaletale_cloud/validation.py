"""Save-time checks for Section 8.3.

Pure functions, no I/O beyond the passed session. The API (M5) calls these
before an insert/update; they are tested here against the schema now.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time, timedelta
from uuid import UUID

from shapely.geometry import Polygon
from sqlalchemy import select
from sqlalchemy.orm import Session

from schemas.enums import TenancyKind
from whaletale_cloud import models as m
from whaletale_cloud.attribution import active_dates


class PolygonError(ValueError):
    pass


def assert_saveable_polygon(points: list[tuple[float, float]] | list[list[float]]) -> None:
    """spec 8.3: reject < 3 points, out-of-frame coordinates, and
    self-intersecting polygons."""
    if len(points) < 3:
        raise PolygonError(f"polygon needs >= 3 points, got {len(points)}")
    for x, y in points:
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            raise PolygonError(f"point ({x}, {y}) is outside the normalized frame")
    poly = Polygon(points)
    if not poly.is_valid or not poly.is_simple:
        raise PolygonError("polygon is self-intersecting")
    if poly.area == 0.0:
        raise PolygonError("polygon has zero area")


@dataclass(frozen=True)
class ProposedTenancy:
    space_id: UUID
    kind: TenancyKind
    starts_on: date
    ends_on: date | None = None
    recurrence_rule: str | None = None
    daily_start_time: time | None = None
    daily_end_time: time | None = None


def find_tenancy_conflicts(
    session: Session,
    proposed: ProposedTenancy,
    *,
    horizon_days: int = 365,
    exclude_tenancy_id: UUID | None = None,
) -> list[m.Tenancy]:
    """Existing tenancies on the same space whose active days (and daily time
    window, for two timed tenancies) overlap the proposed one. Empty list means
    the save is clear (spec 8.3)."""
    window_start = proposed.starts_on
    window_end = proposed.ends_on or (proposed.starts_on + timedelta(days=horizon_days))

    proposed_row = m.Tenancy(
        space_id=proposed.space_id,
        occupant_id=proposed.space_id,  # placeholder, unused by active_dates
        kind=proposed.kind,
        starts_on=proposed.starts_on,
        ends_on=proposed.ends_on,
        recurrence_rule=proposed.recurrence_rule,
        daily_start_time=proposed.daily_start_time,
        daily_end_time=proposed.daily_end_time,
    )
    proposed_days = active_dates(proposed_row, window_start, window_end)
    if not proposed_days:
        return []

    existing = session.scalars(select(m.Tenancy).where(m.Tenancy.space_id == proposed.space_id))
    conflicts: list[m.Tenancy] = []
    for t in existing:
        if exclude_tenancy_id is not None and t.id == exclude_tenancy_id:
            continue
        if not (active_dates(t, window_start, window_end) & proposed_days):
            continue
        if _daily_windows_disjoint(proposed, t):
            continue
        conflicts.append(t)
    return conflicts


def _daily_windows_disjoint(a: ProposedTenancy, b: m.Tenancy) -> bool:
    """True only when both sides have an explicit daily window and the two do
    not overlap. A tenancy with no daily window occupies the whole day."""
    if a.daily_start_time is None or a.daily_end_time is None:
        return False
    if b.daily_start_time is None or b.daily_end_time is None:
        return False
    return a.daily_end_time <= b.daily_start_time or b.daily_end_time <= a.daily_start_time
