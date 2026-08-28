from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from whaletale_cloud import billing
from whaletale_cloud.api.deps import SessionDep
from whaletale_cloud.api.operator.auth import OperatorDep

router = APIRouter(prefix="/v1")


def get_gateway() -> billing.StripeGateway:
    return billing.RealStripeGateway()


GatewayDep = Depends(get_gateway)


class BillingStatusOut(BaseModel):
    status: str
    camera_quantity: int
    billed_cameras: int
    current_period_end: datetime | None
    grace_until: datetime | None
    read_only: bool
    export_ready_at: datetime | None


class ChangePreviewOut(BaseModel):
    current_cameras: int
    new_cameras: int
    prorated_amount_cents: int
    currency: str
    next_invoice_total_cents: int
    effective: datetime
    lines: list[str]


@router.get("/sites/{site_id}/billing", response_model=BillingStatusOut)
def billing_status(session: SessionDep, ctx: OperatorDep, site_id: UUID) -> BillingStatusOut:
    ctx.require_site(site_id)
    sub = billing.get_subscription(session, site_id)
    live = billing.camera_count(session, site_id)
    if sub is None:
        return BillingStatusOut(
            status="none",
            camera_quantity=live,
            billed_cameras=0,
            current_period_end=None,
            grace_until=None,
            read_only=False,
            export_ready_at=None,
        )
    return BillingStatusOut(
        status=sub.status,
        camera_quantity=live,
        billed_cameras=sub.camera_quantity,
        current_period_end=sub.current_period_end,
        grace_until=sub.grace_until,
        read_only=billing.is_read_only(sub),
        export_ready_at=sub.export_ready_at,
    )


@router.get("/sites/{site_id}/billing/preview", response_model=ChangePreviewOut)
def preview(
    session: SessionDep,
    ctx: OperatorDep,
    site_id: UUID,
    gateway: billing.StripeGateway = GatewayDep,
) -> ChangePreviewOut:
    ctx.require_site(site_id)
    try:
        p = billing.preview_change(session, gateway, site_id)
    except billing.BillingError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return ChangePreviewOut(**vars(p))


@router.post("/sites/{site_id}/billing/apply", response_model=BillingStatusOut)
def apply(
    session: SessionDep,
    ctx: OperatorDep,
    site_id: UUID,
    gateway: billing.StripeGateway = GatewayDep,
) -> BillingStatusOut:
    ctx.require_site(site_id)
    try:
        billing.apply_change(session, gateway, site_id)
    except billing.BillingError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return billing_status(session, ctx, site_id)
