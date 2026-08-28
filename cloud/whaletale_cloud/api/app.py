from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from whaletale_cloud.api import heartbeat, ingest
from whaletale_cloud.api.operator import onboarding as operator_onboarding
from whaletale_cloud.api.operator import routes as operator_routes

log = logging.getLogger("whaletale.api")

MAX_BODY_BYTES = 8 * 1024 * 1024  # spec / vibe-check: cap request size


def create_app() -> FastAPI:
    app = FastAPI(title="WhaleTale ingest API", version="0.5.0", docs_url=None, redoc_url=None)

    @app.middleware("http")
    async def limit_body_size(request: Request, call_next):  # type: ignore[no-untyped-def]
        cl = request.headers.get("content-length")
        if cl is not None and cl.isdigit() and int(cl) > MAX_BODY_BYTES:
            return JSONResponse(
                {"detail": "request body too large"},
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            )
        return await call_next(request)

    # No CORS middleware: this API is machine-to-machine (edge boxes over
    # Tailscale), never called from a browser. No default admin route.

    app.include_router(ingest.router)
    app.include_router(heartbeat.router)
    app.include_router(operator_routes.router)
    app.include_router(operator_onboarding.router)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
