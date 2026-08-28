from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select

from schemas.enums import SpaceKind
from whaletale_cloud import models as m
from whaletale_cloud.api.pairing import pair_edge_box

B0 = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def paired(api_client: Any) -> dict[str, Any]:
    """A site with one camera, one space, one zone version, and a paired box."""
    with api_client.db() as s:
        site = m.Site(name="S", timezone="America/Chicago")
        s.add(site)
        s.flush()
        cam = m.Camera(site_id=site.id, name="c", resolution="1920x1080", fps_target=4.0)
        space = m.Space(site_id=site.id, name="Stall 1", kind=SpaceKind.STALL)
        s.add_all([cam, space])
        s.flush()
        zv = m.ZoneVersion(
            space_id=space.id,
            camera_id=cam.id,
            polygon=[[0.1, 0.1], [0.9, 0.1], [0.5, 0.9]],
            is_primary=True,
            effective_from=B0,
            created_by="test",
        )
        s.add(zv)
        s.flush()
        box, token = pair_edge_box(s, site.id, "box-1")
        s.commit()
        return {"site_id": str(site.id), "zv_id": str(zv.id), "token": token, "box_id": str(box.id)}


def _obs(zv_id: str, start: datetime = B0, entries: int = 10) -> dict[str, Any]:
    return {
        "zone_version_id": zv_id,
        "bucket_start": start.isoformat(),
        "bucket_end": (start + timedelta(minutes=15)).isoformat(),
        "entries": entries,
        "exits": entries - 1,
        "peak_occupancy": 3,
        "occupied_seconds": 540.0,
        "dwell_p50_seconds": 42.0,
        "dwell_p90_seconds": 110.0,
        "passersby": 8,
        "capture_events": entries,
    }


def _ingest(client: Any, token: str, body: dict[str, Any]) -> Any:
    return client.post("/v1/ingest", json=body, headers={"Authorization": f"Bearer {token}"})


def test_ingest_upserts_and_is_idempotent(api_client: Any, paired: dict[str, Any]) -> None:
    body = {
        "schema_version": 1,
        "site_id": paired["site_id"],
        "observations": [_obs(paired["zv_id"], entries=10)],
        "site_totals": [
            {
                "site_id": paired["site_id"],
                "bucket_start": B0.isoformat(),
                "total_people": 200,
                "active_cameras": 1,
            }
        ],
    }
    r1 = _ingest(api_client, paired["token"], body)
    assert r1.status_code == 200, r1.text
    assert r1.json() == {"observations_upserted": 1, "site_totals_upserted": 1}

    # resend with a changed value -> still one row, value updated
    body["observations"][0]["entries"] = 99
    r2 = _ingest(api_client, paired["token"], body)
    assert r2.status_code == 200

    with api_client.db() as s:
        assert s.scalar(select(func.count()).select_from(m.Observation)) == 1
        assert s.scalar(select(m.Observation.entries)) == 99
        assert s.scalar(select(func.count()).select_from(m.SiteTotal)) == 1


def test_missing_token_is_401(api_client: Any) -> None:
    r = api_client.post("/v1/ingest", json={"site_id": "x", "observations": []})
    assert r.status_code == 401


def test_bad_token_is_401(api_client: Any, paired: dict[str, Any]) -> None:
    r = _ingest(api_client, "not-a-real-token", {"site_id": paired["site_id"]})
    assert r.status_code == 401


def test_site_id_mismatch_is_403(api_client: Any, paired: dict[str, Any]) -> None:
    r = _ingest(
        api_client,
        paired["token"],
        {"schema_version": 1, "site_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert r.status_code == 403


def test_unknown_zone_version_is_422(api_client: Any, paired: dict[str, Any]) -> None:
    body = {
        "schema_version": 1,
        "site_id": paired["site_id"],
        "observations": [_obs("11111111-1111-1111-1111-111111111111")],
    }
    r = _ingest(api_client, paired["token"], body)
    assert r.status_code == 422


def test_newer_schema_version_is_409(api_client: Any, paired: dict[str, Any]) -> None:
    r = _ingest(
        api_client,
        paired["token"],
        {"schema_version": 99, "site_id": paired["site_id"], "observations": []},
    )
    assert r.status_code == 409


def test_oversized_body_is_413(api_client: Any, paired: dict[str, Any]) -> None:
    r = api_client.post(
        "/v1/ingest",
        content=b"{}",
        headers={
            "Authorization": f"Bearer {paired['token']}",
            "Content-Type": "application/json",
            "Content-Length": str(9 * 1024 * 1024),
        },
    )
    assert r.status_code == 413


def test_security_headers_present_on_every_response(api_client: Any) -> None:
    r = api_client.get("/healthz")
    assert r.status_code == 200
    assert r.headers["strict-transport-security"].startswith("max-age=")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]


def test_rate_limit_returns_429(api_client: Any, paired: dict[str, Any]) -> None:
    api_client.app.state.rate_limiter.limit = 3
    body = {"schema_version": 1, "site_id": paired["site_id"], "observations": []}
    codes = [_ingest(api_client, paired["token"], body).status_code for _ in range(5)]
    assert codes.count(200) == 3
    assert codes.count(429) == 2


def test_heartbeat_is_stored_and_updates_the_box(api_client: Any, paired: dict[str, Any]) -> None:
    hb = {
        "schema_version": 1,
        "site_id": paired["site_id"],
        "agent_version": "0.4.0",
        "uptime_seconds": 3600.0,
        "disk_free_bytes": 12_000_000_000,
        "buckets_pending_sync": 4,
        "per_camera": [{"id": "cam-a", "status": "online", "fps_actual": 3.8}],
    }
    r = api_client.post(
        "/v1/heartbeat", json=hb, headers={"Authorization": f"Bearer {paired['token']}"}
    )
    assert r.status_code == 200, r.text
    assert "received_at" in r.json()

    with api_client.db() as s:
        row = s.scalar(select(m.Heartbeat))
        assert row is not None
        assert row.buckets_pending_sync == 4
        assert row.per_camera[0]["id"] == "cam-a"
        box = s.get(m.EdgeBox, paired["box_id"])
        assert box is not None and box.agent_version == "0.4.0"
        assert box.last_seen_at is not None
