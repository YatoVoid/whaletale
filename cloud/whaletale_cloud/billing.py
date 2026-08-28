"""Stripe billing on camera count (spec 8.5, 12).

- The billed quantity is always the number of `cameras` rows at the site,
  recomputed server-side. A client never sends a price or a quantity.
- Adding a camera charges a proration immediately, after the operator confirms a
  preview. Removing one takes effect at the next period with no mid-period
  refund.
- A failed payment starts a grace window; after it, operator writes go
  read-only. Ingest and heartbeats are never gated - the data gap is
  unrecoverable.
- Cancel offers an export window, then deletion.

Stripe calls go through `StripeGateway` so tests can inject a fake.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from whaletale_cloud import models as m
from whaletale_cloud.config import settings


class BillingError(RuntimeError):
    pass


class WebhookVerificationError(BillingError):
    pass


class StripeGateway(Protocol):
    def preview_quantity_change(
        self, customer_id: str, subscription_id: str, new_quantity: int
    ) -> dict[str, Any]: ...

    def set_quantity(
        self, subscription_id: str, new_quantity: int, *, proration_behavior: str
    ) -> None: ...

    def construct_event(self, payload: bytes, sig_header: str) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ChangePreview:
    current_cameras: int
    new_cameras: int
    prorated_amount_cents: int  # > 0 charged now, < 0 credit
    currency: str
    next_invoice_total_cents: int
    effective: datetime
    lines: list[str]


# --- reads -----------------------------------------------------------


def camera_count(session: Session, site_id: UUID) -> int:
    return int(
        session.scalar(
            select(func.count()).select_from(m.Camera).where(m.Camera.site_id == site_id)
        )
        or 0
    )


def get_subscription(session: Session, site_id: UUID) -> m.Subscription | None:
    return session.scalar(select(m.Subscription).where(m.Subscription.site_id == site_id))


def is_read_only(sub: m.Subscription | None, *, now: datetime | None = None) -> bool:
    """A site goes read-only only after the grace window has fully elapsed
    (spec 8.5). No subscription at all is treated as writable (pre-billing)."""
    if sub is None:
        return False
    now = now or datetime.now(UTC)
    if sub.status == "canceled":
        return True
    if sub.status == "past_due":
        return sub.grace_until is None or now > sub.grace_until
    return False


# --- change flow ----------------------------------------------------


def preview_change(session: Session, gateway: StripeGateway, site_id: UUID) -> ChangePreview:
    sub = _require_sub(session, site_id)
    new_count = camera_count(session, site_id)
    raw = gateway.preview_quantity_change(
        sub.stripe_customer_id, sub.stripe_subscription_id, new_count
    )
    return ChangePreview(
        current_cameras=sub.camera_quantity,
        new_cameras=new_count,
        prorated_amount_cents=int(raw.get("amount_due", 0)),
        currency=str(raw.get("currency", "usd")),
        next_invoice_total_cents=int(raw.get("next_total", raw.get("amount_due", 0))),
        effective=_ts(raw.get("effective")) or datetime.now(UTC),
        lines=[str(x) for x in raw.get("lines", [])],
    )


def apply_change(session: Session, gateway: StripeGateway, site_id: UUID) -> m.Subscription:
    sub = _require_sub(session, site_id)
    new_count = camera_count(session, site_id)
    if new_count == sub.camera_quantity:
        return sub
    # spec 8.5: adds prorate immediately; removes wait for the next period.
    behavior = "create_prorations" if new_count > sub.camera_quantity else "none"
    gateway.set_quantity(sub.stripe_subscription_id, new_count, proration_behavior=behavior)
    sub.camera_quantity = new_count
    sub.updated_at = datetime.now(UTC)
    return sub


# --- webhooks -----------------------------------------------------


_HANDLED = {
    "invoice.payment_failed",
    "invoice.paid",
    "invoice.payment_succeeded",
    "customer.subscription.updated",
    "customer.subscription.deleted",
}


def handle_webhook(
    session: Session, gateway: StripeGateway, payload: bytes, sig_header: str
) -> str:
    try:
        event = gateway.construct_event(payload, sig_header)
    except Exception as exc:  # signature / parse failure
        raise WebhookVerificationError(str(exc)) from exc

    etype = str(event.get("type", ""))
    if etype not in _HANDLED:
        return "ignored"

    obj = event.get("data", {}).get("object", {})
    stripe_sub_id = obj.get("subscription") or obj.get("id")
    sub = session.scalar(
        select(m.Subscription).where(m.Subscription.stripe_subscription_id == stripe_sub_id)
    )
    if sub is None:
        return "no matching subscription"

    now = datetime.now(UTC)
    if etype == "invoice.payment_failed":
        sub.status = "past_due"
        sub.grace_until = now + timedelta(days=settings.billing_grace_days)
    elif etype in ("invoice.paid", "invoice.payment_succeeded"):
        sub.status = "active"
        sub.grace_until = None
    elif etype == "customer.subscription.updated":
        if obj.get("status"):
            sub.status = str(obj["status"])
        sub.current_period_end = _ts(obj.get("current_period_end"))
    elif etype == "customer.subscription.deleted":
        sub.status = "canceled"
        sub.canceled_at = now
        sub.export_ready_at = now + timedelta(days=settings.billing_export_window_days)

    sub.updated_at = now
    return f"applied {etype}"


# --- real gateway ------------------------------------------------


class RealStripeGateway:
    """Thin adapter over the `stripe` SDK. Kept out of the import path until a
    request actually needs it."""

    def __init__(self) -> None:
        import stripe

        if not settings.stripe_secret_key:
            raise BillingError("STRIPE_SECRET_KEY is not set")
        stripe.api_key = settings.stripe_secret_key
        self._stripe = stripe

    def preview_quantity_change(
        self, customer_id: str, subscription_id: str, new_quantity: int
    ) -> dict[str, Any]:
        sub = self._stripe.Subscription.retrieve(subscription_id)
        item_id = sub["items"]["data"][0]["id"]
        # Stripe renamed this across SDK majors (upcoming -> create_preview).
        invoice: Any = self._stripe.Invoice
        upcoming = getattr(invoice, "create_preview", None) or invoice.upcoming
        inv = upcoming(
            customer=customer_id,
            subscription=subscription_id,
            subscription_items=[{"id": item_id, "quantity": new_quantity}],
            subscription_proration_behavior="create_prorations",
        )
        return {
            "amount_due": inv["amount_due"],
            "currency": inv["currency"],
            "next_total": inv["total"],
            "effective": inv.get("period_end"),
            "lines": [ln["description"] for ln in inv["lines"]["data"] if ln.get("description")],
        }

    def set_quantity(
        self, subscription_id: str, new_quantity: int, *, proration_behavior: str
    ) -> None:
        sub = self._stripe.Subscription.retrieve(subscription_id)
        item_id = sub["items"]["data"][0]["id"]
        self._stripe.Subscription.modify(
            subscription_id,
            items=[{"id": item_id, "quantity": new_quantity}],
            proration_behavior=proration_behavior,
        )

    def construct_event(self, payload: bytes, sig_header: str) -> dict[str, Any]:
        if not settings.stripe_webhook_secret:
            raise WebhookVerificationError("STRIPE_WEBHOOK_SECRET is not set")
        return dict(
            self._stripe.Webhook.construct_event(
                payload, sig_header, settings.stripe_webhook_secret
            )
        )


def _require_sub(session: Session, site_id: UUID) -> m.Subscription:
    sub = get_subscription(session, site_id)
    if sub is None:
        raise BillingError("this site has no subscription")
    return sub


def _ts(v: object) -> datetime | None:
    if isinstance(v, int | float):
        return datetime.fromtimestamp(v, UTC)
    return None
