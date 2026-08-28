from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from whaletale_cloud import models as m
from whaletale_cloud.config import settings

ADMIN = "admin-token-under-test"


@pytest.fixture(autouse=True)
def _admin_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "admin_token", ADMIN)


@pytest.fixture
def fleet(api_client: Any) -> Any:
    now = datetime.now(UTC)
    with api_client.db() as s:
        site = m.Site(name="Cedar", timezone="America/Chicago")
        s.add(site)
        s.flush()
        box = m.EdgeBox(
            site_id=site.id,
            name="box-1",
            token_hash="0" * 64,
            agent_version="0.4.0",  # behind
            last_seen_at=now,
        )
        s.add(box)
        s.flush()
        s.add(
            m.Heartbeat(
                edge_box_id=box.id,
                site_id=site.id,
                received_at=now,
                agent_version="0.4.0",
                uptime_seconds=100.0,
                disk_free_bytes=500,
                disk_total_bytes=1000,
                buckets_pending_sync=0,
                last_sync_at=now,
                per_camera=[
                    {"id": "cam-4", "last_frame_at": (now - timedelta(hours=5)).isoformat()}
                ],
            )
        )
        s.commit()
    return api_client


def _h(tok: str = ADMIN) -> dict[str, str]:
    return {"Authorization": f"Bearer {tok}"}


def test_admin_requires_the_token(fleet: Any) -> None:
    assert fleet.get("/admin/fleet").status_code == 401
    assert fleet.get("/admin/fleet", headers=_h("wrong")).status_code == 401
    assert fleet.get("/admin/fleet", headers=_h()).status_code == 200


def test_fleet_reports_state_and_alerts(fleet: Any) -> None:
    body = fleet.get("/admin/fleet", headers=_h()).json()
    assert len(body) == 1
    site = body[0]
    kinds = {a["kind"] for a in site["alerts"]}
    assert "agent_behind" in kinds
    assert "camera_dark" in kinds
    assert site["state"] in {"warning", "critical"}
    cam_alert = next(a for a in site["alerts"] if a["kind"] == "camera_dark")
    assert cam_alert["audience"] == "customer"


def test_evaluate_persists_alerts_and_is_idempotent(fleet: Any) -> None:
    r1 = fleet.post("/admin/fleet/evaluate", headers=_h()).json()
    assert r1["alerts_opened"] >= 2
    r2 = fleet.post("/admin/fleet/evaluate", headers=_h()).json()
    assert r2["alerts_opened"] == 0

    stored = fleet.get("/admin/alerts?audience=customer", headers=_h()).json()
    assert stored and all(a["audience"] == "customer" for a in stored)
    assert all(a["resolved_at"] is None for a in stored)
