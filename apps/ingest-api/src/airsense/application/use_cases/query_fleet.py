"""Read-side use cases backing the dashboard."""

from dataclasses import dataclass

from airsense.application.ports.telemetry import DeviceSnapshot, ReadingRepository
from airsense.domain.telemetry import DeviceId, SensorReading


@dataclass(frozen=True, slots=True)
class ListFleet:
    """Return the latest reading for every device the system has seen."""

    snapshot: DeviceSnapshot

    async def __call__(self) -> list[SensorReading]:
        readings = await self.snapshot.latest()
        return sorted(readings, key=lambda r: r.device_id.value)


@dataclass(frozen=True, slots=True)
class ReadHistory:
    """Return a device's recent readings, oldest first."""

    repository: ReadingRepository

    async def __call__(self, device_id: DeviceId, *, limit: int) -> list[SensorReading]:
        return await self.repository.history(device_id, limit=limit)
