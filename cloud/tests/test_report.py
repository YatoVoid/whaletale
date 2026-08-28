from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from whaletale_cloud import models as m
from whaletale_cloud.metrics import space_metrics
from whaletale_cloud.report import build_report, demo_period
from whaletale_cloud.seed import SITE_TZ, SeedResult

TZ = ZoneInfo(SITE_TZ)


def _week(res: SeedResult, week_index: int) -> tuple[datetime, datetime]:
    start = datetime.combine(
        res.epoch + timedelta(weeks=week_index), time(0), tzinfo=TZ
    ).astimezone(UTC)
    return start, start + timedelta(weeks=1)


def test_headline_numbers_match_the_metrics_layer(seeded: tuple[Session, SeedResult]) -> None:
    db, res = seeded
    start, end = _week(res, 2)
    space_id = res.space_ids["stall-1"]

    d = build_report(db, space_id, start, end)
    ms = space_metrics(db, space_id, start, end)

    assert d.entries == ms.entries
    assert d.capture_rate == ms.capture_rate
    assert d.traffic_share == ms.traffic_share
    assert d.space_name == "Stall 1"
    assert d.period_start == (res.epoch + timedelta(weeks=2))
    assert d.period_end == (res.epoch + timedelta(weeks=2, days=6))


def test_hourly_and_daily_break_down_the_same_total(
    seeded: tuple[Session, SeedResult],
) -> None:
    db, res = seeded
    start, end = _week(res, 3)
    d = build_report(db, res.space_ids["entrance-1"], start, end)
    assert sum(h.entries for h in d.hourly) == d.entries
    assert sum(b.entries for b in d.daily) == d.entries
    assert [b.weekday for b in d.daily] == list(range(7))


def test_occupancy_spans_are_contiguous_and_ordered(
    seeded: tuple[Session, SeedResult],
) -> None:
    db, res = seeded
    start, end = _week(res, 1)
    d = build_report(db, res.space_ids["stall-4"], start, end)
    assert d.occupancy
    assert d.occupancy[0].start == d.period_start
    assert d.occupancy[-1].end == d.period_end
    for a, b in zip(d.occupancy, d.occupancy[1:], strict=False):
        assert b.start == a.end + timedelta(days=1)
        assert a.occupant_name != b.occupant_name


def test_festival_day_shows_in_the_anomaly_table_with_its_annotation(
    seeded: tuple[Session, SeedResult],
) -> None:
    db, res = seeded
    assert res.festival_day is not None
    monday = res.festival_day - timedelta(days=res.festival_day.weekday())
    start = datetime.combine(monday, time(0), tzinfo=TZ).astimezone(UTC)
    d = build_report(db, res.space_ids["entrance-1"], start, start + timedelta(weeks=1))

    festival = [a for a in d.anomalies if a.day == res.festival_day]
    assert len(festival) == 1
    assert festival[0].annotation_kind == "event"
    assert "Festival" in (festival[0].annotation_label or "")
    assert festival[0].entries_z is not None and festival[0].entries_z > 2


def _seed_heartbeats(
    db: Session, res: SeedResult, day: object, *, dip_hours: range, camera: str = "cam-a"
) -> None:
    box = m.EdgeBox(site_id=res.site_id, name="box-1", token_hash="0" * 64)
    db.add(box)
    db.flush()
    for hour in range(6, 20):
        for minute in (0, 15, 30, 45):
            at = datetime.combine(day, time(hour, minute), tzinfo=TZ).astimezone(UTC)  # type: ignore[arg-type]
            conf = 0.30 if hour in dip_hours else 0.85
            db.add(
                m.Heartbeat(
                    id=uuid4(),
                    edge_box_id=box.id,
                    site_id=res.site_id,
                    received_at=at,
                    agent_version="0.10.0",
                    uptime_seconds=3600.0,
                    disk_free_bytes=10**11,
                    buckets_pending_sync=0,
                    per_camera=[{"id": camera, "mean_confidence": conf}],
                )
            )
    db.flush()


def test_low_confidence_buckets_are_counted_from_heartbeats(
    seeded: tuple[Session, SeedResult],
) -> None:
    db, res = seeded
    start, end = _week(res, 2)
    day = res.epoch + timedelta(weeks=2, days=2)  # a mid-week day in the period
    _seed_heartbeats(db, res, day, dip_hours=range(10, 12))  # 10:00-11:45 depressed

    d = build_report(db, res.space_ids["stall-1"], start, end)
    assert d.low_confidence_bucket_count > 0

    # a different week with no heartbeats: nothing flagged
    s3, e3 = _week(res, 3)
    assert build_report(db, res.space_ids["stall-1"], s3, e3).low_confidence_bucket_count == 0


def test_demo_period_picks_a_week_with_a_real_baseline(
    seeded: tuple[Session, SeedResult],
) -> None:
    db, _res = seeded
    space_id, start, end = demo_period(db)
    d = build_report(db, space_id, start, end)
    assert (end - start) == timedelta(weeks=1)
    assert d.entries_vs_self.baseline_n >= 2
