"""HTTP control surface for the simulator."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

import structlog
from fastapi import APIRouter, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from simulator.config import Settings, get_settings
from simulator.logging import configure_logging
from simulator.replay import ReplayEngine, load_trajectories

log = structlog.get_logger("simulator")

limiter = Limiter(key_func=get_remote_address)
router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str


class DeviceState(BaseModel):
    device_id: str
    faulted: bool


class FleetResponse(BaseModel):
    devices: list[DeviceState]
    interval_seconds: float
    replaying: bool


class InjectRequest(BaseModel):
    device_id: str


class InjectResponse(BaseModel):
    device_id: str
    faulted: bool
    detail: str


def _engine(request: Request) -> ReplayEngine:
    engine: ReplayEngine | None = request.app.state.engine
    if engine is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "no replay fixture loaded; generate it with ml/build_replay_fixture.py",
        )
    return engine


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
        devices=[
            DeviceState(device_id=device_id, faulted=engine.is_faulted(device_id))
            for device_id in (engine.device_ids if engine else [])
        ],
        interval_seconds=settings.publish_interval_seconds,
        replaying=engine is not None,
    )


@router.post("/faults/inject", tags=["faults"], summary="Release a device into its fault ramp")
@limiter.limit(lambda: get_settings().inject_rate_limit)  # type: ignore[misc]
async def inject_fault(request: Request, body: InjectRequest) -> InjectResponse:
    engine = _engine(request)
    try:
        engine.inject_fault(body.device_id)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown device: {body.device_id}") from exc

    log.info("fault.injected", device_id=body.device_id)
    return InjectResponse(
        device_id=body.device_id,
        faulted=True,
        detail="device released into its degradation ramp",
    )


@router.post("/faults/reset", tags=["faults"], summary="Return every device to healthy")
@limiter.limit(lambda: get_settings().inject_rate_limit)  # type: ignore[misc]
async def reset_faults(request: Request) -> FleetResponse:
    engine = _engine(request)
    engine.reset_all()
    log.info("fault.reset")
    return await devices(request)


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
        trajectories=load_trajectories(
            settings.fixture_path,
            healthy_ceiling=settings.healthy_ceiling,
            injection_start=settings.fault_injection_start,
        ),
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
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["GET", "POST"],
            allow_headers=["*"],
        )

    app.include_router(router)
    return app
