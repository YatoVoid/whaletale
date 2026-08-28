from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from schemas.enums import BucketQuality
from whaletale_cloud import models as m
from whaletale_cloud.attribution import AttributionRow
from whaletale_cloud.metrics import aggregate, space_metrics
from whaletale_cloud.seed import SITE_TZ, SeedResult

TZ = ZoneInfo(SITE_TZ)


def _row(
    entries: int, passersby: int, *, quality: BucketQuality = BucketQuality.OK
) -> AttributionRow:
    return AttributionRow(
        bucket_start=datetime(2026, 6, 1, tzinfo=UTC),
        bucket_end=datetime(2026, 6, 1, 0, 15, tzinfo=UTC),
        zone_version_id=uuid4(),
        quality=quality,
        occupant_id=None,
        occupant_name=None,
        entries=entries,
        exits=entries,
        peak_occupancy=2,
        occupied_seconds=600.0,
        dwell_p50_seconds=40.0,
        dwell_p90_seconds=120.0,
        passersby=passersby,
        capture_events=entries,
    )


def test_aggregate_of_nothing_is_zero() -> None:
    ms = aggregate([], {})
    assert ms.bucket_count == 0
    assert ms.entries == 0
    assert ms.capture_rate == 0.0
    assert ms.traffic_share is None
    assert ms.person_seconds is None


def test_aggregate_sums_and_capture_rate() -> None:
    rows = [_row(10, 10), _row(30, 10)]
    ms = aggregate(rows, {})
    assert ms.entries == 40
    assert ms.passersby == 20
    assert ms.capture_rate == pytest.approx(40 / 60)


def test_aggregate_counts_degraded_buckets() -> None:
    rows = [_row(5, 1), _row(5, 1, quality=BucketQuality.DEGRADED)]
    assert aggregate(rows, {}).degraded_bucket_count == 1


def test_space_metrics_entries_match_a_direct_observation_sum(
    seeded: tuple[Session, SeedResult],
) -> None:
    db, res = seeded
    start = datetime.combine(res.epoch, time(0), tzinfo=TZ).astimezone(UTC)
    end = start + timedelta(days=7)
    zv = res.primary_zone_version_ids["stall-1"]

    direct = db.execute(
        select(func.coalesce(func.sum(m.Observation.entries), 0)).where(
            m.Observation.zone_version_id == zv,
            m.Observation.bucket_start >= start,
            m.Observation.bucket_start < end,
        )
    ).scalar_one()

    assert space_metrics(db, res.space_ids["stall-1"], start, end).entries == direct


def test_traffic_share_is_a_fraction(seeded: tuple[Session, SeedResult]) -> None:
    db, res = seeded
    start = datetime.combine(res.epoch, time(0), tzinfo=TZ).astimezone(UTC)
    end = start + timedelta(days=7)
    ms = space_metrics(db, res.space_ids["entrance-1"], start, end)
    assert ms.traffic_share is not None
    assert 0.0 < ms.traffic_share <= 1.0


def test_space_metrics_filtered_to_one_occupant(seeded: tuple[Session, SeedResult]) -> None:
    db, res = seeded
    start = datetime.combine(res.epoch, time(0), tzinfo=TZ).astimezone(UTC)
    end = start + timedelta(weeks=6)
    space = res.space_ids["stall-4"]

    everyone = space_metrics(db, space, start, end)
    handbound = space_metrics(
        db, space, start, end, occupant_id=res.occupant_ids["Handbound Books"]
    )
    assert 0 < handbound.entries < everyone.entries
