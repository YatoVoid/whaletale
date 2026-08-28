from __future__ import annotations

from datetime import time, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from schemas.enums import TenancyKind
from whaletale_cloud import models as m
from whaletale_cloud.seed import SeedResult
from whaletale_cloud.validation import (
    PolygonError,
    ProposedTenancy,
    assert_saveable_polygon,
    find_tenancy_conflicts,
)


def test_polygon_needs_three_points() -> None:
    with pytest.raises(PolygonError):
        assert_saveable_polygon([[0.1, 0.1], [0.9, 0.9]])


def test_polygon_must_be_inside_the_frame() -> None:
    with pytest.raises(PolygonError):
        assert_saveable_polygon([[0.1, 0.1], [1.4, 0.2], [0.3, 0.9]])


def test_self_intersecting_polygon_is_rejected() -> None:
    bowtie = [[0.0, 0.0], [1.0, 1.0], [1.0, 0.0], [0.0, 1.0]]
    with pytest.raises(PolygonError):
        assert_saveable_polygon(bowtie)


def test_a_simple_triangle_is_fine() -> None:
    assert_saveable_polygon([[0.2, 0.2], [0.8, 0.3], [0.5, 0.9]])


def test_overlapping_permanent_tenancy_is_a_conflict(seeded: tuple[Session, SeedResult]) -> None:
    db, res = seeded
    proposed = ProposedTenancy(
        space_id=res.space_ids["stall-1"],  # already has Rosa's Tamales, permanent
        kind=TenancyKind.PERMANENT,
        starts_on=res.epoch + timedelta(days=3),
    )
    conflicts = find_tenancy_conflicts(db, proposed)
    assert len(conflicts) == 1


def test_non_overlapping_dates_are_clear(seeded: tuple[Session, SeedResult]) -> None:
    db, res = seeded
    # stall-4: Handbound Books ends at the gap start; propose a tenancy that
    # starts after it ends and before the next one.
    assert res.vacant_gap is not None
    gap_start, _gap_end = res.vacant_gap
    proposed = ProposedTenancy(
        space_id=res.space_ids["stall-4"],
        kind=TenancyKind.ONE_OFF,
        starts_on=gap_start + timedelta(days=2),
        ends_on=gap_start + timedelta(days=2),
    )
    assert find_tenancy_conflicts(db, proposed) == []


def test_recurring_tenancies_on_different_weekdays_do_not_conflict(
    seeded: tuple[Session, SeedResult],
) -> None:
    db, res = seeded
    # stall-3 has a Saturday recurring tenancy; a Sunday one is fine.
    proposed = ProposedTenancy(
        space_id=res.space_ids["stall-3"],
        kind=TenancyKind.RECURRING,
        starts_on=res.epoch,
        recurrence_rule="FREQ=WEEKLY;BYDAY=SU",
    )
    assert find_tenancy_conflicts(db, proposed, horizon_days=60) == []


def test_same_weekday_but_disjoint_daily_windows_do_not_conflict(
    seeded: tuple[Session, SeedResult],
) -> None:
    db, res = seeded
    # stall-3's Saturday tenant runs 08:00-14:00; an afternoon slot is clear.
    proposed = ProposedTenancy(
        space_id=res.space_ids["stall-3"],
        kind=TenancyKind.RECURRING,
        starts_on=res.epoch,
        recurrence_rule="FREQ=WEEKLY;BYDAY=SA",
        daily_start_time=time(14, 0),
        daily_end_time=time(18, 0),
    )
    assert find_tenancy_conflicts(db, proposed, horizon_days=60) == []


def test_same_weekday_overlapping_daily_windows_conflict(
    seeded: tuple[Session, SeedResult],
) -> None:
    db, res = seeded
    proposed = ProposedTenancy(
        space_id=res.space_ids["stall-3"],
        kind=TenancyKind.RECURRING,
        starts_on=res.epoch,
        recurrence_rule="FREQ=WEEKLY;BYDAY=SA",
        daily_start_time=time(12, 0),
        daily_end_time=time(16, 0),
    )
    assert len(find_tenancy_conflicts(db, proposed, horizon_days=60)) == 1


def test_editing_a_tenancy_does_not_conflict_with_itself(
    seeded: tuple[Session, SeedResult],
) -> None:
    db, res = seeded
    existing = db.scalars(
        select(m.Tenancy).where(m.Tenancy.space_id == res.space_ids["stall-1"])
    ).one()
    proposed = ProposedTenancy(
        space_id=res.space_ids["stall-1"],
        kind=TenancyKind.PERMANENT,
        starts_on=existing.starts_on,
    )
    assert find_tenancy_conflicts(db, proposed, exclude_tenancy_id=existing.id) == []
