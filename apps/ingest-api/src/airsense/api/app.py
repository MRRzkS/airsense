"""FastAPI application factory and composition root."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from airsense.api.routers import devices, health, stream
from airsense.api.services import Services
from airsense.application.use_cases.ingest_reading import IngestReading
from airsense.application.use_cases.query_fleet import ListFleet, ReadHistory
from airsense.infrastructure.config import Settings, get_settings
from airsense.infrastructure.db.reading_repository import TimescaleReadingRepository
from airsense.infrastructure.db.session import create_engine, create_session_factory
from airsense.infrastructure.logging import configure_logging
from airsense.infrastructure.mqtt.subscriber import MqttTelemetrySubscriber
from airsense.infrastructure.onnx.scorer import create_scorer
from airsense.infrastructure.probes import DependencyProbe
from airsense.infrastructure.redis.hub import RedisTelemetryHub, create_client


@dataclass(frozen=True, slots=True)
class Runtime:
    """Wired services plus the connections that own them, so shutdown can close both."""

    services: Services
    subscriber: MqttTelemetrySubscriber
    engine: AsyncEngine
    client: Redis


def build_runtime(settings: Settings) -> Runtime:
    engine = create_engine(settings.database_dsn)
    client = create_client(settings.redis_dsn)

    # One Redis adapter satisfies both the snapshot and the stream port.
    hub = RedisTelemetryHub(client)
    repository = TimescaleReadingRepository(create_session_factory(engine))
    ingest = IngestReading(
        repository=repository,
        snapshot=hub,
        stream=hub,
        scorer=create_scorer(settings.model_path, settings.feature_spec_path),
    )

    services = Services(
        stream=hub,
        probe=DependencyProbe(engine=engine, client=client),
        ingest=ingest,
        list_fleet=ListFleet(snapshot=hub),
        read_history=ReadHistory(repository=repository),
    )
    subscriber = MqttTelemetrySubscriber(
        host=settings.mqtt_host,
        port=settings.mqtt_port,
        topic_prefix=settings.mqtt_topic_prefix,
        client_id=settings.mqtt_client_id,
        ingest=ingest,
    )
    return Runtime(services=services, subscriber=subscriber, engine=engine, client=client)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    log = structlog.get_logger(settings.service_name)

    runtime = build_runtime(settings)
    app.state.services = runtime.services

    task = asyncio.create_task(runtime.subscriber.run(), name="mqtt-ingest")
    log.info(
        "service.startup",
        version=settings.service_version,
        environment=settings.environment,
        ticket_sink=settings.ticket_sink,
    )
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        await runtime.client.aclose()
        await runtime.engine.dispose()
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
    app.include_router(devices.router)
    app.include_router(stream.router)
    app.mount("/metrics", make_asgi_app())
    return app
