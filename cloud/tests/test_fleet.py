from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from whaletale_cloud import models as m
from whaletale_cloud.fleet import FleetConfig, evaluate_fleet, sync_alerts

NOW = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)
CFG = FleetConfig(current_agent_version="0.9.0")


def _site_box(
    db: Session, *, box_seen: datetime | None, agent: str | None
) -> tuple[m.Site, m.EdgeBox]:
    site = m.Site(name="Cedar", timezone="America/Chicago")
    db.add(site)
    db.flush()
    box = m.EdgeBox(
        site_id=site.id,
        name="box-1",
        token_hash="0" * 64,
        agent_version=agent,
        last_seen_at=box_seen,
    )
    db.add(box)
    db.flush()
    return site, box


def _hb(db: Session, box: m.EdgeBox, site: m.Site, **kw: object) -> m.Heartbeat:
    defaults: dict[str, object] = dict(
        received_at=NOW,
        agent_version=box.agent_version or "0.9.0",
        uptime_seconds=3600.0,
        disk_free_bytes=500_000_000_000,
        disk_total_bytes=1_000_000_000_000,
        buckets_pending_sync=0,
        last_sync_at=NOW,
        per_camera=[],
    )
    defaults.update(kw)
    hb = m.Heartbeat(edge_box_id=box.id, site_id=site.id, **defaults)
    db.add(hb)
    db.flush()
    return hb


def test_healthy_box_has_no_alerts(clean_db: Session) -> None:
    site, box = _site_box(clean_db, box_seen=NOW, agent="0.9.0")
    _hb(clean_db, box, site, per_camera=[{"id": "cam-a", "last_frame_at": NOW.isoformat()}])
    [sh] = evaluate_fleet(clean_db, now=NOW, config=CFG)
    assert sh.alerts == []
    assert sh.state == "ok"
    assert sh.boxes[0].online is True


def test_never_reported_box(clean_db: Session) -> None:
    _site_box(clean_db, box_seen=None, agent="0.9.0")
    [sh] = evaluate_fleet(clean_db, now=NOW, config=CFG)
    assert [a.kind for a in sh.alerts] == ["never_reported"]


def test_agent_behind_alerts_us(clean_db: Session) -> None:
    site, box = _site_box(clean_db, box_seen=NOW, agent="0.4.0")
    _hb(clean_db, box, site)
    [sh] = evaluate_fleet(clean_db, now=NOW, config=CFG)
    a = next(a for a in sh.alerts if a.kind == "agent_behind")
    assert a.audience == "us"
    assert "0.4.0" in a.message


def test_sync_stale(clean_db: Session) -> None:
    site, box = _site_box(clean_db, box_seen=NOW, agent="0.9.0")
    _hb(clean_db, box, site, last_sync_at=NOW - timedelta(hours=30))
    [sh] = evaluate_fleet(clean_db, now=NOW, config=CFG)
    a = next(a for a in sh.alerts if a.kind == "sync_stale")
    assert a.severity == "critical"


def test_disk_low(clean_db: Session) -> None:
    site, box = _site_box(clean_db, box_seen=NOW, agent="0.9.0")
    _hb(clean_db, box, site, disk_free_bytes=50_000_000_000)  # 5%
    [sh] = evaluate_fleet(clean_db, now=NOW, config=CFG)
    a = next(a for a in sh.alerts if a.kind == "disk_low")
    assert a.severity == "critical"
    assert "5% free" in a.message


def test_camera_dark_alerts_the_customer_in_plain_language(clean_db: Session) -> None:
    site, box = _site_box(clean_db, box_seen=NOW, agent="0.9.0")
    _hb(
        clean_db,
        box,
        site,
        per_camera=[{"id": "cam-4", "last_frame_at": (NOW - timedelta(hours=3)).isoformat()}],
    )
    [sh] = evaluate_fleet(clean_db, now=NOW, config=CFG)
    a = next(a for a in sh.alerts if a.kind == "camera_dark")
    assert a.audience == "customer"
    assert a.message.startswith("Camera cam-4 has been offline since")
    assert "power" in a.message


def test_camera_moved_alerts_the_customer(clean_db: Session) -> None:
    site, box = _site_box(clean_db, box_seen=NOW, agent="0.9.0")
    _hb(
        clean_db,
        box,
        site,
        per_camera=[
            {
                "id": "cam-2",
                "status": "needs_recalibration",
                "last_frame_at": NOW.isoformat(),
            }
        ],
    )
    [sh] = evaluate_fleet(clean_db, now=NOW, config=CFG)
    a = next(a for a in sh.alerts if a.kind == "camera_moved")
    assert a.audience == "customer"
    assert "moved" in a.message and "calibration" in a.message
    # a moved camera is not also reported as a confidence drop
    assert not any(al.kind == "low_confidence" and al.subject == "cam-2" for al in sh.alerts)


def test_confidence_drop_from_baseline(clean_db: Session) -> None:
    site, box = _site_box(clean_db, box_seen=NOW, agent="0.9.0")
    for i in range(5):  # baseline ~0.80
        _hb(
            clean_db,
            box,
            site,
            received_at=NOW - timedelta(minutes=10 * (i + 1)),
            per_camera=[
                {
                    "id": "cam-a",
                    "last_frame_at": NOW.isoformat(),
                    "mean_confidence": 0.80,
                }
            ],
        )
    _hb(
        clean_db,
        box,
        site,
        per_camera=[{"id": "cam-a", "last_frame_at": NOW.isoformat(), "mean_confidence": 0.40}],
    )
    [sh] = evaluate_fleet(clean_db, now=NOW, config=CFG)
    assert any(a.kind == "low_confidence" for a in sh.alerts)


def test_sync_alerts_opens_then_resolves(clean_db: Session) -> None:
    site, box = _site_box(clean_db, box_seen=NOW, agent="0.4.0")
    _hb(clean_db, box, site)

    opened = sync_alerts(clean_db, evaluate_fleet(clean_db, now=NOW, config=CFG), now=NOW)
    assert opened == 1
    # idempotent — a second run opens nothing new
    assert sync_alerts(clean_db, evaluate_fleet(clean_db, now=NOW, config=CFG), now=NOW) == 0

    # condition clears: upgrade the box
    box.agent_version = "0.9.0"
    clean_db.flush()
    sync_alerts(
        clean_db, evaluate_fleet(clean_db, now=NOW, config=CFG), now=NOW + timedelta(hours=1)
    )
    row = clean_db.scalars(select(m.Alert)).one()
    assert row.resolved_at is not None
