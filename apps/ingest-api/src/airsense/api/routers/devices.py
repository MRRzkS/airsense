"""Fleet read endpoints."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from airsense.api.deps import ServicesDep
from airsense.domain.telemetry import DeviceId
from airsense.infrastructure.wire import TelemetryMessage

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("", summary="Latest reading for every known device")
async def list_devices(services: ServicesDep) -> list[TelemetryMessage]:
    readings = await services.list_fleet()
    return [TelemetryMessage.from_domain(reading) for reading in readings]


@router.get("/{device_id}/readings", summary="Recent history for one device")
async def read_history(
    device_id: str,
    services: ServicesDep,
    limit: Annotated[int, Query(ge=1, le=2000)] = 300,
) -> list[TelemetryMessage]:
    try:
        identifier = DeviceId(device_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    readings = await services.read_history(identifier, limit=limit)
    return [TelemetryMessage.from_domain(reading) for reading in readings]
