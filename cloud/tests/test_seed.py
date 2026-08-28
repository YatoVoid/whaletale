from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from whaletale_cloud import models as m
from whaletale_cloud.seed import SITE_TZ, seed_demo


def _utc_midnight(day: date) -> datetime:
    return datetime.combine(day, time(0), tzinfo=ZoneInfo(SITE_TZ))


def test_seed_is_deterministic_and_well_formed(clean_db: Session) -> None:
    seed_demo(clean_db, weeks=3)

    counts = {
        t.__name__: clean_db.scalar(select(func.count()).select_from(t))
        for t in (m.Site, m.Camera, m.Space, m.ZoneVersion, m.Occupant, m.Tenancy)
    }
    assert counts["Site"] == 1
    assert counts["Space"] == 11
    assert counts["Camera"] == 3
    # 11 spaces, stall-3 reshaped into two versions, patio-1 has a failover.
    assert counts["ZoneVersion"] == 11 + 1 + 1
    assert counts["Tenancy"] == 9

    observations = clean_db.scalar(select(func.count()).select_from(m.Observation))
    assert observations and observations > 1000


def test_seed_reshape_has_one_open_primary_and_a_closed_prior(clean_db: Session) -> None:
    res = seed_demo(clean_db, weeks=4)
    versions = (
        clean_db.execute(
            select(m.ZoneVersion)
            .where(m.ZoneVersion.space_id == res.space_ids[res.reshaped_space])
            .order_by(m.ZoneVersion.effective_from)
        )
        .scalars()
        .all()
    )
    assert len(versions) == 2
    assert versions[0].effective_to == res.reshape_at_utc
    assert versions[1].effective_to is None
    assert all(v.is_primary for v in versions)


def test_seed_no_observations_on_the_closure_day(clean_db: Session) -> None:
    res = seed_demo(clean_db, weeks=3)
    assert res.closure_day is not None
    day_zones = select(m.ZoneVersion.id).where(
        m.ZoneVersion.space_id.in_(list(res.space_ids.values()))
    )
    rows = clean_db.execute(
        select(func.count())
        .select_from(m.Observation)
        .where(
            m.Observation.zone_version_id.in_(day_zones),
            m.Observation.bucket_start >= _utc_midnight(res.closure_day),
            m.Observation.bucket_start < _utc_midnight(res.closure_day) + timedelta(days=1),
        )
    ).scalar_one()
    assert rows == 0


def test_seed_festival_day_beats_a_normal_saturday(clean_db: Session) -> None:
    res = seed_demo(clean_db, weeks=5)
    assert res.festival_day is not None
    entrance_zv = res.primary_zone_version_ids["entrance-1"]

    def day_entries(day: date) -> int:
        return clean_db.execute(
            select(func.coalesce(func.sum(m.Observation.entries), 0)).where(
                m.Observation.zone_version_id == entrance_zv,
                m.Observation.bucket_start >= _utc_midnight(day),
                m.Observation.bucket_start < _utc_midnight(day) + timedelta(days=1),
            )
        ).scalar_one()

    normal_saturday = res.festival_day - timedelta(days=7)
    assert day_entries(res.festival_day) > 2 * day_entries(normal_saturday)
