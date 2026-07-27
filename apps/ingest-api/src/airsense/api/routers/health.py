"""Liveness and readiness probes consumed by compose healthchecks and CI."""

from fastapi import APIRouter
from pydantic import BaseModel

from airsense.api.deps import SettingsDep

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
async def ready(settings: SettingsDep) -> ReadinessResponse:
    """Report whether every downstream dependency is reachable.

    Returns an empty check map until the database, cache and broker clients are
    wired in P1; the contract is that an empty map means nothing is claimed.
    """
    checks: dict[str, str] = {}
    status = "ready" if all(v == "ok" for v in checks.values()) else "degraded"
    return ReadinessResponse(status=status, checks=checks)
