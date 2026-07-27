"""In-memory doubles for every outbound port.

These exist because `Services` is built from Protocols rather than concrete
adapters: the whole HTTP surface is testable without a database, a cache, a
broker or a model.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from airsense.domain.conditions import ConditionPolicy, ConditionState, DeviceCondition
from airsense.domain.scoring import ScoredReading
from airsense.domain.severity import SeverityPolicy
from airsense.domain.telemetry import Channel, DeviceId, SensorReading
from airsense.domain.ticketing import TicketPolicy

NOMINAL: dict[Channel, float] = {
    Channel.COMPRESSOR_CURRENT: 4.6,
    Channel.DISCHARGE_PRESSURE: 2780.0,
    Channel.SUCTION_TEMPERATURE: 7.1,
    Channel.AMBIENT_TEMPERATURE: 26.4,
    Channel.VIBRATION_RMS: 1.1,
}

EPOCH = datetime(2026, 7, 27, 9, 0, tzinfo=UTC)


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
        recorded_at=EPOCH + timedelta(seconds=sequence),
        sequence=sequence,
        channels=channels,
    )


def make_scored(
    device_id: str = "AC-0001",
    sequence: int = 0,
    health_index: float | None = None,
    condition: DeviceCondition = DeviceCondition.NORMAL,
    **overrides: float,
) -> ScoredReading:
    return ScoredReading(
        reading=make_reading(device_id, sequence, **overrides),
        health_index=health_index,
        condition=condition,
    )


# Shared policy values for tests that exercise orchestration rather than
# thresholds. Rule tests build their own so the numbers under test are visible
# in the test that depends on them.
DEMO_CONDITION_POLICY = ConditionPolicy(
    watch_enter=0.50,
    watch_exit=0.40,
    alert_enter=0.75,
    alert_exit=0.65,
    sustained_samples=3,
)
DEMO_SEVERITY_POLICY = SeverityPolicy(
    medium_band=0.60,
    high_band=0.75,
    critical_band=0.90,
    fast_degradation_per_sample=0.05,
)
DEMO_TICKET_POLICY = TicketPolicy(cooldown=timedelta(minutes=30))


@dataclass(slots=True)
class InMemoryConditionStore:
    states: dict[str, ConditionState] = field(default_factory=dict)

    async def load(self, device_id: DeviceId) -> ConditionState:
        return self.states.get(device_id.value, ConditionState())

    async def save(self, device_id: DeviceId, state: ConditionState) -> None:
        self.states[device_id.value] = state


@dataclass(slots=True)
class StubScorer:
    """Returns a fixed score, or None to mimic a device still warming up."""

    value: float | None = 0.25
    seen: list[SensorReading] = field(default_factory=list)

    def score(self, reading: SensorReading) -> float | None:
        self.seen.append(reading)
        return self.value


@dataclass(slots=True)
class InMemoryReadingRepository:
    rows: list[ScoredReading] = field(default_factory=list)

    async def append(self, scored: ScoredReading) -> None:
        self.rows.append(scored)

    async def history(self, device_id: DeviceId, *, limit: int) -> list[ScoredReading]:
        matching = [row for row in self.rows if row.reading.device_id == device_id]
        return matching[-limit:]


@dataclass(slots=True)
class ExplodingReadingRepository:
    error: Exception = field(default_factory=lambda: RuntimeError("database unavailable"))

    async def append(self, scored: ScoredReading) -> None:
        raise self.error

    async def history(self, device_id: DeviceId, *, limit: int) -> list[ScoredReading]:
        raise self.error


@dataclass(slots=True)
class InMemorySnapshot:
    by_device: dict[str, ScoredReading] = field(default_factory=dict)

    async def remember(self, scored: ScoredReading) -> None:
        self.by_device[scored.reading.device_id.value] = scored

    async def latest(self) -> list[ScoredReading]:
        return list(self.by_device.values())


@dataclass(slots=True)
class InMemoryStream:
    published: list[ScoredReading] = field(default_factory=list)

    async def publish(self, scored: ScoredReading) -> None:
        self.published.append(scored)

    async def subscribe(self) -> AsyncIterator[ScoredReading]:
        for scored in self.published:
            yield scored


@dataclass(slots=True)
class StubDependencyHealth:
    result: dict[str, str] = field(
        default_factory=lambda: {"database": "ok", "cache": "ok"},
    )

    async def check(self) -> dict[str, str]:
        return self.result
