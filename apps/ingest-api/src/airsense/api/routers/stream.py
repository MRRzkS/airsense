"""Server-sent events carrying live telemetry to the dashboard."""

from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from airsense.api.deps import ServicesDep
from airsense.infrastructure.wire import TelemetryMessage

router = APIRouter(tags=["stream"])


@router.get("/stream", summary="Live telemetry as server-sent events")
async def stream(request: Request, services: ServicesDep) -> EventSourceResponse:
    async def events() -> AsyncIterator[dict[str, str]]:
        async for reading in services.stream.subscribe():
            if await request.is_disconnected():
                break
            yield {
                "event": "reading",
                "data": TelemetryMessage.from_domain(reading).model_dump_json(),
            }

    return EventSourceResponse(events())
