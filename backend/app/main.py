from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.errors import install_error_handlers
from app.api.routes import admin, clinical, me, orders, screenings, shop
from app.context import build_context
from app.core.config import Settings, get_settings
from app.core.db import Base
import app.models  # noqa: F401  (register tables)


class SecurityHeaders(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        return resp


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or get_settings()
    ctx = build_context(settings)
    prod = settings.is_production
    app = FastAPI(title="C-Diab API", version="1.0.0", docs_url=None if prod else "/docs", redoc_url=None,
                  openapi_url=None if prod else "/openapi.json")
    app.state.ctx = ctx
    app.add_middleware(SecurityHeaders)
    if settings.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])
    install_error_handlers(app)
    for r in (me.router, screenings.router, shop.router, orders.router, admin.router, clinical.router):
        app.include_router(r, prefix="/api/v1")

    @app.get("/health", tags=["meta"])
    def health():
        return {"status": "ok", "env": settings.app_env, "ai_backend": settings.ai_backend,
                "payment_provider": settings.payment_provider, "policy_version": ctx.policy.version,
                "policy_clinically_approved": ctx.policy.is_approved}

    if settings.database_url.startswith("sqlite"):  # local dev/tests only; production schema comes from SQL migrations
        Base.metadata.create_all(ctx.engine)
    return app
