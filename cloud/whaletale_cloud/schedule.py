"""Resolve who holds each space on each day, independent of whether any camera
observed traffic - this is the schedule grid (spec 10.3), not a metrics view.

Reuses the same tenancy rules as attribution: earliest-created tenancy wins a
day, a `closure` annotation blanks the day, recurring tenancies expand by RRULE.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from schemas.enums import DayAnnotationKind
from whaletale_cloud import models as m
from whaletale_cloud.attribution import active_dates


def resolve_schedule(
    session: Session, site_id: UUID, start: date, end: date
) -> dict[tuple[UUID, date], str | None]:
    """{(space_id, day): occupant_name or None} for every day in [start, end]."""
    spaces = list(
        session.scalars(
            select(m.Space).where(m.Space.site_id == site_id, m.Space.archived_at.is_(None))
        )
    )
    tenancies_by_space: dict[UUID, list[m.Tenancy]] = defaultdict(list)
    for t in session.scalars(
        select(m.Tenancy)
        .join(m.Space, m.Space.id == m.Tenancy.space_id)
        .where(m.Space.site_id == site_id)
        .order_by(m.Tenancy.created_at)
    ):
        tenancies_by_space[t.space_id].append(t)

    occupant_names = {
        o.id: o.name
        for o in session.scalars(select(m.Occupant).where(m.Occupant.site_id == site_id))
    }
    closures = {
        d
        for d in session.scalars(
            select(m.DayAnnotation.day).where(
                m.DayAnnotation.site_id == site_id,
                m.DayAnnotation.kind == DayAnnotationKind.CLOSURE,
                m.DayAnnotation.day >= start,
                m.DayAnnotation.day <= end,
            )
        )
    }

    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    grid: dict[tuple[UUID, date], str | None] = {}
    for space in spaces:
        active: dict[UUID, set[date]] = {
            t.id: active_dates(t, start, end) for t in tenancies_by_space[space.id]
        }
        for day in days:
            name: str | None = None
            if day not in closures:
                for t in tenancies_by_space[space.id]:  # created_at order
                    if day in active[t.id]:
                        name = occupant_names.get(t.occupant_id)
                        break
            grid[(space.id, day)] = name
    return grid
