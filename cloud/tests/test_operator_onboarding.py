from __future__ import annotations

from typing import Any

import pytest

from whaletale_cloud import models as m
from whaletale_cloud.api.operator.auth import create_operator_user


@pytest.fixture
def op(api_client: Any) -> dict[str, Any]:
    with api_client.db() as s:
        site = m.Site(name="Cedar", timezone="America/Chicago")
        s.add(site)
        s.flush()
        _u, token = create_operator_user(s, "mgr@example.test", [site.id])
        s.commit()
        return {"client": api_client, "token": token, "site_id": str(site.id)}


def _h(op: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {op['token']}"}


def test_pair_edge_box_returns_a_token_once(op: dict[str, Any]) -> None:
    r = op["client"].post(
        f"/v1/sites/{op['site_id']}/edge-boxes", json={"name": "box-1"}, headers=_h(op)
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["pairing_token"]
    box_id = body["id"]

    # the token is not persisted in plaintext — the list view never returns it
    lst = op["client"].get(f"/v1/sites/{op['site_id']}/edge-boxes", headers=_h(op)).json()
    assert [b["id"] for b in lst] == [box_id]
    assert "pairing_token" not in lst[0]

    with op["client"].db() as s:
        box = s.get(m.EdgeBox, box_id)
        assert box is not None
        assert box.token_hash != body["pairing_token"]
        assert len(box.token_hash) == 64  # sha256 hex


def test_register_and_list_cameras(op: dict[str, Any]) -> None:
    r = op["client"].post(
        f"/v1/sites/{op['site_id']}/cameras",
        json={
            "name": "front-hall",
            "resolution": "1920x1080",
            "fps_target": 4.0,
            "rtsp_url_encrypted": "gAAAAA...",
        },
        headers=_h(op),
    )
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "online"

    cams = op["client"].get(f"/v1/sites/{op['site_id']}/cameras", headers=_h(op)).json()
    assert [c["name"] for c in cams] == ["front-hall"]
    assert cams[0]["resolution"] == "1920x1080"


def test_bad_resolution_is_422(op: dict[str, Any]) -> None:
    r = op["client"].post(
        f"/v1/sites/{op['site_id']}/cameras",
        json={"name": "c", "resolution": "huge", "fps_target": 4.0},
        headers=_h(op),
    )
    assert r.status_code == 422


def test_revoke_box_drops_it_from_the_list(op: dict[str, Any]) -> None:
    box_id = (
        op["client"]
        .post(f"/v1/sites/{op['site_id']}/edge-boxes", json={}, headers=_h(op))
        .json()["id"]
    )
    assert op["client"].post(f"/v1/edge-boxes/{box_id}/revoke", headers=_h(op)).status_code == 204
    lst = op["client"].get(f"/v1/sites/{op['site_id']}/edge-boxes", headers=_h(op)).json()
    assert lst == []


def test_other_site_cannot_pair(op: dict[str, Any]) -> None:
    r = op["client"].post(
        "/v1/sites/00000000-0000-0000-0000-000000000000/edge-boxes",
        json={},
        headers=_h(op),
    )
    assert r.status_code == 403
