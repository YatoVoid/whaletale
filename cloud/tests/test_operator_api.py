from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select

from whaletale_cloud import models as m
from whaletale_cloud.api.operator.auth import create_operator_user
from whaletale_cloud.seed import SeedResult, seed_demo


@pytest.fixture
def op(api_client: Any) -> dict[str, Any]:
    with api_client.db() as s:
        res: SeedResult = seed_demo(s, weeks=4)
        other = m.Site(name="Not Mine", timezone="America/Chicago")
        s.add(other)
        s.flush()
        _user, token = create_operator_user(s, "mgr@example.test", [res.site_id])
        s.commit()
    return {"client": api_client, "token": token, "res": res, "other_site_id": str(other.id)}


def _get(op: dict[str, Any], path: str, **params: Any) -> Any:
    return op["client"].get(
        path, params=params or None, headers={"Authorization": f"Bearer {op['token']}"}
    )


def _post(op: dict[str, Any], path: str, body: Any) -> Any:
    return op["client"].post(path, json=body, headers={"Authorization": f"Bearer {op['token']}"})


def test_sites_are_scoped_to_the_user(op: dict[str, Any]) -> None:
    r = _get(op, "/v1/sites")
    assert r.status_code == 200
    ids = {s["id"] for s in r.json()}
    assert ids == {str(op["res"].site_id)}
    assert op["other_site_id"] not in ids


def test_no_token_is_401(op: dict[str, Any]) -> None:
    assert op["client"].get("/v1/sites").status_code == 401


def test_other_site_is_403(op: dict[str, Any]) -> None:
    assert _get(op, f"/v1/sites/{op['other_site_id']}/spaces").status_code == 403


def test_spaces_list_resolves_current_occupant(op: dict[str, Any]) -> None:
    r = _get(op, f"/v1/sites/{op['res'].site_id}/spaces")
    assert r.status_code == 200
    by_name = {s["name"]: s for s in r.json()}
    assert len(by_name) == 11
    assert by_name["Stall 1"]["current_occupant"] == "Rosa's Tamales"
    assert by_name["Stall 6"]["current_occupant"] is None
    assert by_name["Stall 6"]["archived"] is False


def test_space_detail_has_metrics_and_occupancy(op: dict[str, Any]) -> None:
    res = op["res"]
    space_id = res.space_ids["stall-1"]
    start = res.epoch + timedelta(weeks=2)
    r = _get(
        op,
        f"/v1/spaces/{space_id}",
        start=start.isoformat(),
        end=(start + timedelta(days=6)).isoformat(),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["metrics"]["entries"] > 0
    assert 0.0 <= body["metrics"]["capture_rate"] <= 1.0
    assert body["occupancy"]
    assert body["space"]["current_occupant"] == "Rosa's Tamales"


def test_schedule_grid_has_vacant_cells(op: dict[str, Any]) -> None:
    res = op["res"]
    start = res.epoch + timedelta(weeks=1)
    r = _get(
        op,
        f"/v1/sites/{res.site_id}/schedule",
        start=start.isoformat(),
        end=(start + timedelta(days=6)).isoformat(),
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["days"]) == 7
    never_leased = str(res.space_ids["stall-6"])
    cells = [c for c in body["cells"] if c["space_id"] == never_leased]
    assert cells and all(c["occupant_name"] is None for c in cells)
    # stall-1 has a permanent tenant; the one blank day is the seeded closure.
    stall1 = [c for c in body["cells"] if c["space_id"] == str(res.space_ids["stall-1"])]
    names = [c["occupant_name"] for c in stall1]
    assert names.count("Rosa's Tamales") == 6
    assert names.count(None) == 1


def test_create_and_rename_occupant(op: dict[str, Any]) -> None:
    site_id = op["res"].site_id
    r = _post(op, f"/v1/sites/{site_id}/occupants", {"name": "New Vendor"})
    assert r.status_code == 201
    occ_id = r.json()["id"]
    r2 = op["client"].patch(
        f"/v1/occupants/{occ_id}",
        json={"name": "New Vendor LLC"},
        headers={"Authorization": f"Bearer {op['token']}"},
    )
    assert r2.status_code == 200
    assert r2.json()["name"] == "New Vendor LLC"


def test_create_tenancy_then_conflict(op: dict[str, Any]) -> None:
    res = op["res"]
    space_id = res.space_ids["stall-6"]  # currently unleased
    occ_id = str(res.occupant_ids["Blue Ridge Coffee"])
    body = {
        "occupant_id": occ_id,
        "kind": "permanent",
        "starts_on": res.epoch.isoformat(),
    }
    r = _post(op, f"/v1/spaces/{space_id}/tenancies", body)
    assert r.status_code == 201, r.text

    # a second overlapping permanent tenancy -> 409 naming the conflict
    body2 = dict(body, occupant_id=str(res.occupant_ids["Marisol Flowers"]))
    r2 = _post(op, f"/v1/spaces/{space_id}/tenancies", body2)
    assert r2.status_code == 409
    assert r2.json()["detail"]["conflicting_tenancy_ids"]


def test_reshape_zone_creates_a_new_version(op: dict[str, Any]) -> None:
    res = op["res"]
    space_id = res.space_ids["stall-1"]
    body = {
        "polygon": [[0.2, 0.3], [0.8, 0.3], [0.8, 0.9], [0.2, 0.9]],
        "created_by": "mgr@example.test",
    }
    r = _post(op, f"/v1/spaces/{space_id}/zone-versions/reshape", body)
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["version_number"] == 2
    assert "version 2" in out["message"]

    with op["client"].db() as s:
        versions = list(s.scalars(select(m.ZoneVersion).where(m.ZoneVersion.space_id == space_id)))
        assert len(versions) == 2
        assert sum(1 for v in versions if v.effective_to is None) == 1


def test_current_zone_returns_the_open_primary(op: dict[str, Any]) -> None:
    space_id = op["res"].space_ids["stall-1"]
    r = _get(op, f"/v1/spaces/{space_id}/zone-versions/current")
    assert r.status_code == 200, r.text
    cur = r.json()
    assert cur["version_number"] == 1
    assert len(cur["polygon"]) >= 3


def test_reshape_conflicts_when_base_version_is_stale(op: dict[str, Any]) -> None:
    # spec 8.4: two operators edit the same zone. The second save carries the
    # id it loaded, which the first save already superseded.
    space_id = op["res"].space_ids["stall-1"]
    stale = _get(op, f"/v1/spaces/{space_id}/zone-versions/current").json()["zone_version_id"]
    poly = [[0.2, 0.3], [0.8, 0.3], [0.8, 0.9], [0.2, 0.9]]

    first = _post(
        op,
        f"/v1/spaces/{space_id}/zone-versions/reshape",
        {"polygon": poly, "created_by": "a@example.test", "base_version_id": stale},
    )
    assert first.status_code == 201, first.text

    second = _post(
        op,
        f"/v1/spaces/{space_id}/zone-versions/reshape",
        {"polygon": poly, "created_by": "b@example.test", "base_version_id": stale},
    )
    assert second.status_code == 409
    assert "changed since you opened it" in second.json()["detail"]


def test_reshape_rejects_a_self_intersecting_polygon(op: dict[str, Any]) -> None:
    space_id = op["res"].space_ids["stall-1"]
    body = {
        "polygon": [[0.0, 0.0], [1.0, 1.0], [1.0, 0.0], [0.0, 1.0]],
        "created_by": "mgr@example.test",
    }
    r = _post(op, f"/v1/spaces/{space_id}/zone-versions/reshape", body)
    assert r.status_code == 422


def test_overview_ranks_spaces_and_lists_vacancies(op: dict[str, Any]) -> None:
    res = op["res"]
    start = res.epoch + timedelta(weeks=2)
    r = _get(
        op,
        f"/v1/sites/{res.site_id}/overview",
        start=start.isoformat(),
        end=(start + timedelta(days=6)).isoformat(),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    rates = [s["capture_rate"] for s in body["spaces"]]
    assert rates == sorted(rates, reverse=True)
    assert str(res.space_ids["stall-6"]) in body["vacant_space_ids"]
    assert body["boxes_total"] == 0


def test_space_report_pdf(op: dict[str, Any]) -> None:
    res = op["res"]
    space_id = res.space_ids["entrance-1"]
    start = res.epoch + timedelta(weeks=2)
    r = _get(
        op,
        f"/v1/spaces/{space_id}/report.pdf",
        start=start.isoformat(),
        end=(start + timedelta(days=6)).isoformat(),
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:5] == b"%PDF-"
