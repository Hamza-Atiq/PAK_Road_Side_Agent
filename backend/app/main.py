"""FastAPI application factory.

Wires up:
- CORS for the three frontend SPAs
- structlog with trace_id middleware
- slowapi rate limiting on auth endpoints
- All API routers (auth so far; more added in later phases)
- Health and metrics endpoints
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api import admin as admin_router
from app.api import auth as auth_router
from app.api import incidents as incidents_router
from app.api import providers as providers_router
from app.api import setup as setup_router
from app.api import webhooks as webhooks_router
from app.api import ws as ws_router
from app.config import settings
from app.database import engine
from app.middleware.logging import TraceIDMiddleware, configure_logging, get_logger
from app.middleware.metrics import HTTPMetricsMiddleware, metrics_endpoint

# Import the Celery app so its broker/result configuration becomes the
# `current_app` for any @shared_task `.delay()` calls made from API handlers.
# Without this import the default Celery app is used, which tries AMQP on
# localhost:5672 and fails (WinError 10061).
import celery_worker  # noqa: F401

# Reuse the limiter defined alongside the auth routes so @limiter.limit on
# those endpoints is the same Limiter instance attached to app.state.
limiter = auth_router.limiter


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    log = get_logger("startup")
    log.info(
        "app_starting",
        env=settings.APP_ENV,
        debug=settings.DEBUG,
        app_name=settings.APP_NAME,
    )
    yield
    log.info("app_shutting_down")
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="RoadSide Agent API",
        version="0.1.0",
        description="Fully agentic global roadside assistance platform.",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # ---------- Rate limiter ----------
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    # ---------- CORS ----------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Trace-Id"],
    )

    # ---------- Trace IDs + structured logging ----------
    app.add_middleware(TraceIDMiddleware)

    # ---------- HTTP latency / status metrics ----------
    if settings.PROMETHEUS_ENABLED:
        app.add_middleware(HTTPMetricsMiddleware)

    # ---------- Routers ----------
    app.include_router(auth_router.router)
    app.include_router(webhooks_router.router)
    app.include_router(admin_router.router)
    app.include_router(incidents_router.router)
    app.include_router(providers_router.router)
    app.include_router(ws_router.router)
    app.include_router(setup_router.router)

    # ---------- Static uploads ----------
    upload_dir = Path(settings.UPLOAD_DIR).resolve()
    upload_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=str(upload_dir)), name="uploads")

    # ---------- Health ----------
    @app.get("/health", tags=["meta"], summary="Health check")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": settings.APP_NAME, "env": settings.APP_ENV}

    # ---------- Prometheus scrape endpoint ----------
    if settings.PROMETHEUS_ENABLED:
        @app.get("/metrics", include_in_schema=False, tags=["meta"])
        async def _metrics():
            return metrics_endpoint()

    # ---------- Unhandled exception logger ----------
    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log = get_logger("unhandled")
        log.exception(
            "unhandled_exception",
            path=request.url.path,
            method=request.method,
            error=str(exc),
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "internal server error"},
        )

    return app


app = create_app()
