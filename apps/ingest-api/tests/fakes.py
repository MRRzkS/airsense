"""In-memory doubles for every outbound port.

These exist because `Services` is built from Protocols rather than concrete
adapters: the whole HTTP surface is testable without a database, a cache or a
broker.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime

from airsense.domain.telemetry import Channel, DeviceId, SensorReading

NOMINAL: dict[Channel, float] = {
    Channel.COMPRESSOR_CURRENT: 4.6,
    Channel.DISCHARGE_PRESSURE: 2780.0,
    Channel.SUCTION_TEMPERATURE: 7.1,
    Channel.AMBIENT_TEMPERATURE: 26.4,
    Channel.VIBRATION_RMS: 1.1,
}


def make_reading(
    device_id: str = "AC-0001",
    sequence: int = 0,
    **overrides: float,
) -> SensorReading:
    channels = dict(NOMINAL)
    for name, value in overrides.items():
        channels[Channel(name)] = value
    return SensorReading.from_channels(
        device_id=DeviceId(device_id),
        recorded_at=datetime.now(UTC),
        sequence=sequence,
        channels=channels,
    )


@dataclass(slots=True)
class InMemoryReadingRepository:
    rows: list[SensorReading] = field(default_factory=list)

    async def append(self, reading: SensorReading) -> None:
        self.rows.append(reading)

    async def history(self, device_id: DeviceId, *, limit: int) -> list[SensorReading]:
        matching = [row for row in self.rows if row.device_id == device_id]
        return matching[-limit:]


@dataclass(slots=True)
class ExplodingReadingRepository:
    error: Exception = field(default_factory=lambda: RuntimeError("database unavailable"))

    async def append(self, reading: SensorReading) -> None:
        raise self.error

    async def history(self, device_id: DeviceId, *, limit: int) -> list[SensorReading]:
        raise self.error


@dataclass(slots=True)
class InMemorySnapshot:
    by_device: dict[str, SensorReading] = field(default_factory=dict)

    async def remember(self, reading: SensorReading) -> None:
        self.by_device[reading.device_id.value] = reading

    async def latest(self) -> list[SensorReading]:
        return list(self.by_device.values())


@dataclass(slots=True)
class InMemoryStream:
    published: list[SensorReading] = field(default_factory=list)

    async def publish(self, reading: SensorReading) -> None:
        self.published.append(reading)

    async def subscribe(self) -> AsyncIterator[SensorReading]:
        for reading in self.published:
            yield reading


@dataclass(slots=True)
class StubDependencyHealth:
    result: dict[str, str] = field(
        default_factory=lambda: {"database": "ok", "cache": "ok"},
    )

    async def check(self) -> dict[str, str]:
        return self.result
