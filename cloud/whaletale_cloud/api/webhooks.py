from __future__ import annotations

from fastapi import APIRouter, Header, Request, status
from fastapi.responses import JSONResponse

from whaletale_cloud import billing
from whaletale_cloud.api.deps import get_session
from whaletale_cloud.api.operator.billing import get_gateway

router = APIRouter(prefix="/webhooks")


@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None),
) -> JSONResponse:
    payload = await request.body()
    gateway = get_gateway()
    gen = get_session()
    session = next(gen)
    try:
        result = billing.handle_webhook(session, gateway, payload, stripe_signature or "")
        session.commit()
    except billing.WebhookVerificationError:
        session.rollback()
        return JSONResponse(
            {"detail": "signature verification failed"},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    return JSONResponse({"result": result})
