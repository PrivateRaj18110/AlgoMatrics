"""Raj Quant OS — FastAPI application entry point.

Run locally with:

    uvicorn main:app --reload

Exposes the full Trading Operations Center API (machines, strategies, trades,
brokers, accounts, analytics, risk, execution, events, logs, alerts, settings),
the ``monitor_sdk`` ingestion endpoints and a websocket live feed. Data is
served from in-memory mock repositories until Supabase is wired up.
"""

from contextlib import asynccontextmanager

import asyncio

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import get_settings
from app.database.seed import seed_if_empty
from app.middleware.cors import configure_cors
from app.middleware.gzip_request import GzipRequestMiddleware
from app.realtime.publisher import publish_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Seed demo data (DB mode) and start the websocket publisher."""
    seed_if_empty()
    task = asyncio.create_task(publish_loop())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


def create_app() -> FastAPI:
    """Application factory — builds and configures the FastAPI instance."""
    settings = get_settings()

    # Refuse to serve a production configuration that would be unsafe: no
    # database (telemetry lost on restart, deduplication disabled), no agent
    # credential (open telemetry write path), or no dashboard credential (open
    # telemetry read path). Raising here stops the container before it binds,
    # which is the point — the alternative is a healthy-looking service quietly
    # doing the wrong thing.
    settings.assert_production_ready()

    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description="Trading Operations Center API for Raj Quant OS.",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    configure_cors(app)
    # Transparently decompress gzip request bodies (agent batch uploads).
    app.add_middleware(GzipRequestMiddleware)
    app.include_router(api_router, prefix=settings.api_prefix)

    @app.get("/", tags=["system"], summary="Service root")
    def root() -> dict[str, str]:
        """Minimal root payload pointing clients at the docs + health check."""
        return {
            "service": settings.app_name,
            "version": settings.version,
            "docs": "/docs",
            "health": f"{settings.api_prefix}/health",
        }

    return app


app = create_app()
