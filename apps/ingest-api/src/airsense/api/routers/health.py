"""Liveness and readiness probes consumed by compose healthchecks and CI."""

from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from airsense.api.deps import ServicesDep, SettingsDep

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str


class ReadinessResponse(BaseModel):
    status: str
    checks: dict[str, str]


@router.get("/health", summary="Liveness probe")
async def health(settings: SettingsDep) -> HealthResponse:
    """Report that the process is running. Never touches a dependency."""
    return HealthResponse(
        status="ok",
        service=settings.service_name,
        version=settings.service_version,
        environment=settings.environment,
    )


@router.get("/ready", summary="Readiness probe")
async def ready(services: ServicesDep, response: Response) -> ReadinessResponse:
    """Report whether every downstream dependency is reachable.

    Answers 503 when any check fails so a load balancer stops routing here,
    while still naming the failing dependency in the body.
    """
    checks = await services.probe.check()
    ready = all(value == "ok" for value in checks.values())
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(status="ready" if ready else "degraded", checks=checks)
