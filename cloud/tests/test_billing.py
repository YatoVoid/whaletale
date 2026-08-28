from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from whaletale_cloud import billing
from whaletale_cloud import models as m


class FakeGateway:
    def __init__(self, preview: dict[str, Any] | None = None) -> None:
        self._preview = preview or {
            "amount_due": 1200,
            "currency": "usd",
            "next_total": 3600,
            "lines": ["1 additional camera (prorated)"],
        }
        self.set_calls: list[tuple[int, str]] = []
        self.event: dict[str, Any] = {}

    def preview_quantity_change(self, c: str, s: str, q: int) -> dict[str, Any]:
        return self._preview

    def set_quantity(self, s: str, q: int, *, proration_behavior: str) -> None:
        self.set_calls.append((q, proration_behavior))

    def construct_event(self, payload: bytes, sig: str) -> dict[str, Any]:
        if sig == "bad":
            raise ValueError("signature mismatch")
        return self.event


def _site_sub(db: Session, *, qty: int = 2, status: str = "active") -> tuple[UUID, m.Subscription]:
    site = m.Site(name="Cedar", timezone="America/Chicago")
    db.add(site)
    db.flush()
    sub = m.Subscription(
        site_id=site.id,
        stripe_customer_id="cus_1",
        stripe_subscription_id="sub_1",
        stripe_price_id="price_1",
        status=status,
        camera_quantity=qty,
    )
    db.add(sub)
    db.flush()
    return site.id, sub


def _cameras(db: Session, site_id: UUID, n: int) -> None:
    for i in range(n):
        db.add(m.Camera(site_id=site_id, name=f"c{i}", resolution="1920x1080", fps_target=4.0))
    db.flush()


# --- read-only rules -----------------------------------------------


def test_no_subscription_is_writable() -> None:
    assert billing.is_read_only(None) is False


def test_past_due_is_writable_during_grace_then_read_only() -> None:
    now = datetime(2026, 6, 10, tzinfo=UTC)
    sub = m.Subscription(
        site_id=UUID(int=0),
        stripe_customer_id="",
        stripe_subscription_id="",
        stripe_price_id="",
        status="past_due",
        camera_quantity=1,
        grace_until=now + timedelta(days=2),
    )
    assert billing.is_read_only(sub, now=now) is False
    assert billing.is_read_only(sub, now=now + timedelta(days=3)) is True


def test_canceled_is_read_only() -> None:
    sub = m.Subscription(
        site_id=UUID(int=0),
        stripe_customer_id="",
        stripe_subscription_id="",
        stripe_price_id="",
        status="canceled",
        camera_quantity=1,
    )
    assert billing.is_read_only(sub) is True


# --- change flow --------------------------------------------------


def test_preview_reflects_the_live_camera_count(clean_db: Session) -> None:
    site_id, _sub = _site_sub(clean_db, qty=2)
    _cameras(clean_db, site_id, 3)
    p = billing.preview_change(clean_db, FakeGateway(), site_id)
    assert p.current_cameras == 2
    assert p.new_cameras == 3
    assert p.prorated_amount_cents == 1200


def test_apply_add_prorates_immediately(clean_db: Session) -> None:
    site_id, sub = _site_sub(clean_db, qty=2)
    _cameras(clean_db, site_id, 4)
    gw = FakeGateway()
    billing.apply_change(clean_db, gw, site_id)
    assert gw.set_calls == [(4, "create_prorations")]
    assert sub.camera_quantity == 4


def test_apply_remove_defers_to_next_period(clean_db: Session) -> None:
    site_id, sub = _site_sub(clean_db, qty=3)
    _cameras(clean_db, site_id, 1)
    gw = FakeGateway()
    billing.apply_change(clean_db, gw, site_id)
    assert gw.set_calls == [(1, "none")]
    assert sub.camera_quantity == 1


def test_apply_noop_when_unchanged(clean_db: Session) -> None:
    site_id, _sub = _site_sub(clean_db, qty=2)
    _cameras(clean_db, site_id, 2)
    gw = FakeGateway()
    billing.apply_change(clean_db, gw, site_id)
    assert gw.set_calls == []


# --- webhooks ---------------------------------------------------


def test_payment_failed_then_paid(clean_db: Session) -> None:
    _site_id, sub = _site_sub(clean_db)
    gw = FakeGateway()

    gw.event = {"type": "invoice.payment_failed", "data": {"object": {"subscription": "sub_1"}}}
    billing.handle_webhook(clean_db, gw, b"{}", "sig")
    assert sub.status == "past_due"
    assert sub.grace_until is not None

    gw.event = {"type": "invoice.paid", "data": {"object": {"subscription": "sub_1"}}}
    billing.handle_webhook(clean_db, gw, b"{}", "sig")
    assert sub.status == "active"
    assert sub.grace_until is None


def test_subscription_deleted_starts_export_window(clean_db: Session) -> None:
    _site_id, sub = _site_sub(clean_db)
    gw = FakeGateway()
    gw.event = {"type": "customer.subscription.deleted", "data": {"object": {"id": "sub_1"}}}
    billing.handle_webhook(clean_db, gw, b"{}", "sig")
    assert sub.status == "canceled"
    assert sub.export_ready_at is not None


def test_bad_signature_raises(clean_db: Session) -> None:
    with pytest.raises(billing.WebhookVerificationError):
        billing.handle_webhook(clean_db, FakeGateway(), b"{}", "bad")


# --- API gating (spec 8.5) ------------------------------------


def _op(api_client: Any) -> dict[str, Any]:
    from whaletale_cloud.api.operator.auth import create_operator_user

    with api_client.db() as s:
        site_id, sub = _site_sub(s, qty=1, status="past_due")
        sub.grace_until = datetime.now(UTC) - timedelta(days=1)  # grace expired
        cam = m.Camera(site_id=site_id, name="c", resolution="1920x1080", fps_target=4.0)
        space = m.Space(site_id=site_id, name="Stall 1", kind="stall")
        s.add_all([cam, space])
        s.flush()
        zv = m.ZoneVersion(
            space_id=space.id,
            camera_id=cam.id,
            polygon=[[0.1, 0.1], [0.9, 0.1], [0.5, 0.9]],
            is_primary=True,
            effective_from=datetime.now(UTC),
            created_by="t",
        )
        s.add(zv)
        s.flush()
        _u, otok = create_operator_user(s, "mgr@x.test", [site_id])
        from whaletale_cloud.api.pairing import pair_edge_box

        _box, btok = pair_edge_box(s, site_id)
        s.commit()
        return {
            "client": api_client,
            "site_id": str(site_id),
            "zv_id": str(zv.id),
            "otok": otok,
            "btok": btok,
        }


def test_operator_write_is_402_when_read_only(api_client: Any) -> None:
    op = _op(api_client)
    r = api_client.post(
        f"/v1/sites/{op['site_id']}/occupants",
        json={"name": "New"},
        headers={"Authorization": f"Bearer {op['otok']}"},
    )
    assert r.status_code == 402


def test_operator_read_still_works_when_read_only(api_client: Any) -> None:
    op = _op(api_client)
    r = api_client.get("/v1/sites", headers={"Authorization": f"Bearer {op['otok']}"})
    assert r.status_code == 200


def test_ingest_is_never_gated_by_billing(api_client: Any) -> None:
    op = _op(api_client)
    body = {
        "schema_version": 1,
        "site_id": op["site_id"],
        "observations": [
            {
                "zone_version_id": op["zv_id"],
                "bucket_start": "2026-06-01T12:00:00+00:00",
                "bucket_end": "2026-06-01T12:15:00+00:00",
                "entries": 3,
                "exits": 3,
                "peak_occupancy": 1,
                "occupied_seconds": 100.0,
                "dwell_p50_seconds": 20.0,
                "dwell_p90_seconds": 40.0,
                "passersby": 1,
                "capture_events": 3,
            }
        ],
    }
    r = api_client.post("/v1/ingest", json=body, headers={"Authorization": f"Bearer {op['btok']}"})
    assert r.status_code == 200, r.text
