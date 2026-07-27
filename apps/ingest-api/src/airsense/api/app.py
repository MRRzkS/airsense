"""FastAPI application factory and composition root."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from airsense.api.routers import health
from airsense.infrastructure.config import Settings, get_settings
from airsense.infrastructure.logging import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    log = structlog.get_logger(settings.service_name)
    log.info(
        "service.startup",
        version=settings.service_version,
        environment=settings.environment,
        ticket_sink=settings.ticket_sink,
    )
    yield
    log.info("service.shutdown")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build a fully wired application. Adapters are selected here and nowhere else."""
    settings = settings or get_settings()
    configure_logging(level=settings.log_level, json_output=settings.emit_json_logs)

    app = FastAPI(
        title="airsense ingest-api",
        version=settings.service_version,
        summary="Telemetry ingest, degradation scoring and ticketing for connected AC units",
        lifespan=lifespan,
    )
    app.state.settings = settings

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["GET", "POST"],
            allow_headers=["*"],
        )

    app.include_router(health.router)
    app.mount("/metrics", make_asgi_app())
    return app
