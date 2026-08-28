from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from schemas.enums import BucketQuality, DayAnnotationKind, TenancyKind
from whaletale_cloud import models as m
from whaletale_cloud.attribution import attribute_space
from whaletale_cloud.seed import SITE_TZ, SeedResult

TZ = ZoneInfo(SITE_TZ)


def _window(res: SeedResult, day_from: int, day_to: int) -> tuple[datetime, datetime]:
    start = datetime.combine(res.epoch + timedelta(days=day_from), time(0), tzinfo=TZ)
    end = datetime.combine(res.epoch + timedelta(days=day_to), time(0), tzinfo=TZ)
    return start.astimezone(UTC), end.astimezone(UTC)


def test_permanent_tenancy_attributes_every_bucket(seeded: tuple[Session, SeedResult]) -> None:
    db, res = seeded
    rows = attribute_space(db, res.space_ids["stall-1"], *_window(res, 0, 7))
    assert rows
    assert all(r.occupant_name == "Rosa's Tamales" for r in rows)
    assert all(r.quality is BucketQuality.OK for r in rows)


def test_never_leased_space_is_all_vacant(seeded: tuple[Session, SeedResult]) -> None:
    db, res = seeded
    rows = attribute_space(db, res.space_ids[res.never_leased_space], *_window(res, 0, 7))
    assert rows
    assert all(r.is_vacant for r in rows)
    assert all(r.occupant_id is None for r in rows)


def test_tenancy_gap_reads_as_vacant_between_two_occupants(
    seeded: tuple[Session, SeedResult],
) -> None:
    db, res = seeded
    assert res.vacant_gap is not None
    gap_start, gap_end = res.vacant_gap
    before = attribute_space(db, res.space_ids["stall-4"], *_window(res, 1, 2))
    during = attribute_space(
        db,
        res.space_ids["stall-4"],
        *_window(res, (gap_start - res.epoch).days + 1, (gap_start - res.epoch).days + 3),
    )
    after = attribute_space(
        db,
        res.space_ids["stall-4"],
        *_window(res, (gap_end - res.epoch).days, (gap_end - res.epoch).days + 1),
    )
    assert {r.occupant_name for r in before} == {"Handbound Books"}
    assert during and all(r.is_vacant for r in during)
    assert {r.occupant_name for r in after} == {"Vetiver & Ash"}


def test_recurring_tenancy_is_saturday_only_and_within_daily_window(
    seeded: tuple[Session, SeedResult],
) -> None:
    db, res = seeded
    rows = attribute_space(db, res.space_ids["stall-3"], *_window(res, 0, 14))
    assert rows

    for r in rows:
        local = r.bucket_start.astimezone(TZ)
        occupied = r.occupant_name == "The Pickle Cart"
        in_window = local.weekday() == 5 and time(8, 0) <= local.time() < time(14, 0)
        assert occupied == in_window, (local.isoformat(), occupied)


def test_one_off_tenancy_covers_a_single_local_day(seeded: tuple[Session, SeedResult]) -> None:
    db, res = seeded
    rows = attribute_space(db, res.space_ids["stall-5"], *_window(res, 0, 20))
    occupied_days = {
        r.bucket_start.astimezone(TZ).date() for r in rows if r.occupant_name == "Marisol Flowers"
    }
    assert occupied_days == {res.epoch + timedelta(days=12)}


def test_reshape_resolves_the_zone_version_effective_per_bucket(
    seeded: tuple[Session, SeedResult],
) -> None:
    db, res = seeded
    assert res.reshape_at_utc is not None
    rows = attribute_space(db, res.space_ids[res.reshaped_space], *_window(res, 14, 28))
    assert rows
    v1, v2 = res.reshape_v1_zone_version_id, res.primary_zone_version_ids[res.reshaped_space]
    for r in rows:
        expected = v2 if r.bucket_start >= res.reshape_at_utc else v1
        assert r.zone_version_id == expected


def test_closure_annotation_suppresses_an_otherwise_occupied_bucket(
    seeded: tuple[Session, SeedResult],
) -> None:
    db, res = seeded
    # A normal Wednesday in week 2 that has observations and a permanent tenant.
    target = res.epoch + timedelta(days=9)
    db.add(
        m.DayAnnotation(
            id=uuid4(),
            site_id=res.site_id,
            day=target,
            kind=DayAnnotationKind.CLOSURE,
            label="test closure",
            exclude_from_baseline=True,
            created_by="test",
        )
    )
    db.flush()
    start = datetime.combine(target, time(0), tzinfo=TZ).astimezone(UTC)
    rows = attribute_space(db, res.space_ids["stall-1"], start, start + timedelta(days=1))
    assert rows
    assert all(r.is_vacant for r in rows)


def test_degraded_when_primary_bucket_missing_and_secondary_has_it(
    seeded: tuple[Session, SeedResult],
) -> None:
    db, res = seeded
    space_id = res.space_ids[res.failover_space]
    primary_id = res.primary_zone_version_ids[res.failover_space]
    secondary_id = db.scalar(
        select(m.ZoneVersion.id).where(
            m.ZoneVersion.space_id == space_id, m.ZoneVersion.is_primary.is_(False)
        )
    )
    assert secondary_id is not None

    start_utc, end_utc = _window(res, 2, 3)
    primary_obs = list(
        db.scalars(
            select(m.Observation).where(
                m.Observation.zone_version_id == primary_id,
                m.Observation.bucket_start >= start_utc,
                m.Observation.bucket_start < end_utc,
            )
        )
    )
    assert primary_obs
    moved = {o.bucket_start for o in primary_obs}
    for o in primary_obs:
        db.add(
            m.Observation(
                id=uuid4(),
                zone_version_id=secondary_id,
                bucket_start=o.bucket_start,
                bucket_end=o.bucket_end,
                entries=o.entries,
                exits=o.exits,
                peak_occupancy=o.peak_occupancy,
                occupied_seconds=o.occupied_seconds,
                dwell_p50_seconds=o.dwell_p50_seconds,
                dwell_p90_seconds=o.dwell_p90_seconds,
                passersby=o.passersby,
                capture_events=o.capture_events,
            )
        )
    db.execute(
        delete(m.Observation).where(
            m.Observation.zone_version_id == primary_id,
            m.Observation.bucket_start.in_(list(moved)),
        )
    )
    db.flush()

    rows = attribute_space(db, space_id, start_utc, end_utc)
    assert rows
    assert all(r.quality is BucketQuality.DEGRADED for r in rows)
    assert all(r.zone_version_id == secondary_id for r in rows)


def test_retroactive_tenancy_edit_recomputes(seeded: tuple[Session, SeedResult]) -> None:
    db, res = seeded
    space_id = res.space_ids[res.never_leased_space]
    win = _window(res, 0, 5)
    assert all(r.is_vacant for r in attribute_space(db, space_id, *win))

    db.add(
        m.Tenancy(
            id=uuid4(),
            space_id=space_id,
            occupant_id=res.occupant_ids["Blue Ridge Coffee"],
            kind=TenancyKind.PERMANENT,
            starts_on=res.epoch,
            created_at=datetime.now(UTC),
        )
    )
    db.flush()
    assert all(r.occupant_name == "Blue Ridge Coffee" for r in attribute_space(db, space_id, *win))


def test_occupant_rename_propagates_to_history(seeded: tuple[Session, SeedResult]) -> None:
    db, res = seeded
    win = _window(res, 0, 3)
    occ = db.get(m.Occupant, res.occupant_ids["Rosa's Tamales"])
    assert occ is not None
    occ.name = "Rosa's Tamales & Café"
    db.flush()
    rows = attribute_space(db, res.space_ids["stall-1"], *win)
    assert {r.occupant_name for r in rows} == {"Rosa's Tamales & Café"}


def test_overlapping_tenancies_resolve_to_the_earliest_created(
    seeded: tuple[Session, SeedResult],
) -> None:
    db, res = seeded
    space_id = res.space_ids[res.never_leased_space]
    first = datetime.now(UTC)
    db.add_all(
        [
            m.Tenancy(
                id=uuid4(),
                space_id=space_id,
                occupant_id=res.occupant_ids["Foothill Cheese"],
                kind=TenancyKind.PERMANENT,
                starts_on=res.epoch,
                created_at=first,
            ),
            m.Tenancy(
                id=uuid4(),
                space_id=space_id,
                occupant_id=res.occupant_ids["Marisol Flowers"],
                kind=TenancyKind.PERMANENT,
                starts_on=res.epoch,
                created_at=first + timedelta(hours=1),
            ),
        ]
    )
    db.flush()
    rows = attribute_space(db, space_id, *_window(res, 0, 3))
    assert {r.occupant_name for r in rows} == {"Foothill Cheese"}
