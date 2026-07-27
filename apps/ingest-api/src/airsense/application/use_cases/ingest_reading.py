"""Ingest one telemetry reading."""

from dataclasses import dataclass

from airsense.application.ports.telemetry import (
    DeviceSnapshot,
    ReadingRepository,
    TelemetryStream,
)
from airsense.domain.telemetry import SensorReading


@dataclass(frozen=True, slots=True)
class IngestReading:
    """Persist a reading, then cache it, then fan it out.

    The order is the contract. History is the only durable record, so it is
    written first: a dashboard that misses a frame recovers on the next one,
    whereas a reading dropped before persistence is gone. Cache and stream
    failures must therefore not prevent the write.
    """

    repository: ReadingRepository
    snapshot: DeviceSnapshot
    stream: TelemetryStream

    async def __call__(self, reading: SensorReading) -> None:
        await self.repository.append(reading)
        await self.snapshot.remember(reading)
        await self.stream.publish(reading)
