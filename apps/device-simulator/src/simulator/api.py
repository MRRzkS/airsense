"""HTTP control surface for the simulator."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

import structlog
from fastapi import APIRouter, FastAPI, Request
from pydantic import BaseModel

from simulator.config import Settings, get_settings
from simulator.logging import configure_logging
from simulator.replay import ReplayEngine, load_tracks

log = structlog.get_logger("simulator")

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str


class FleetResponse(BaseModel):
    devices: list[str]
    interval_seconds: float
    replaying: bool


@router.get("/health", tags=["health"], summary="Liveness probe")
async def health(request: Request) -> HealthResponse:
    settings: Settings = request.app.state.settings
    return HealthResponse(
        status="ok",
        service=settings.service_name,
        version=settings.service_version,
        environment=settings.environment,
    )


@router.get("/devices", tags=["fleet"], summary="Devices this simulator publishes")
async def devices(request: Request) -> FleetResponse:
    settings: Settings = request.app.state.settings
    engine: ReplayEngine | None = request.app.state.engine
    return FleetResponse(
        devices=engine.device_ids if engine else [],
        interval_seconds=settings.publish_interval_seconds,
        replaying=engine is not None,
    )


def build_engine(settings: Settings) -> ReplayEngine | None:
    """Load the replay fixture, or return None with a loud log if it is absent.

    Missing data degrades to an idle-but-healthy service rather than a crash
    loop: a container restarting every five seconds hides the actual message.
    """
    if not settings.fixture_path.exists():
        log.error(
            "fixture.missing",
            path=str(settings.fixture_path),
            hint="generate it with ml/build_replay_fixture.py",
        )
        return None

    return ReplayEngine(
        tracks=load_tracks(settings.fixture_path),
        host=settings.mqtt_host,
        port=settings.mqtt_port,
        topic_prefix=settings.mqtt_topic_prefix,
        client_id=settings.mqtt_client_id,
        interval_seconds=settings.publish_interval_seconds,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    engine = build_engine(settings)
    app.state.engine = engine

    task = asyncio.create_task(engine.run(), name="replay") if engine is not None else None
    log.info("service.startup", version=settings.service_version, broker=settings.mqtt_host)
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
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
    app.state.engine = None
    app.include_router(router)
    return app
