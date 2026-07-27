"""HTTP control surface for the simulator."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from pydantic import BaseModel

from simulator.config import Settings, get_settings
from simulator.logging import configure_logging


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    log = structlog.get_logger(settings.service_name)
    log.info("service.startup", version=settings.service_version, broker=settings.mqtt_host)
    yield
    log.info("service.shutdown")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the simulator's control API."""
    settings = settings or get_settings()
    configure_logging(level=settings.log_level, json_output=settings.emit_json_logs)

    app = FastAPI(
        title="airsense device-simulator",
        version=settings.service_version,
        summary="Replays telemetry to MQTT and injects faults on demand",
        lifespan=lifespan,
    )
    app.state.settings = settings

    @app.get("/health", tags=["health"], summary="Liveness probe")
    async def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            service=settings.service_name,
            version=settings.service_version,
            environment=settings.environment,
        )

    return app
