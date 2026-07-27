"""Outbound ports for the telemetry path.

Three separate needs, deliberately not one interface: durable history, latest
known state, and live fan-out have different failure modes and different
backing stores. `infrastructure` may satisfy more than one with a single
adapter; the application does not need to know that.
"""

from collections.abc import AsyncIterator
from typing import Protocol

from airsense.domain.scoring import ScoredReading
from airsense.domain.telemetry import DeviceId


class ReadingRepository(Protocol):
    """Durable, append-only history."""

    async def append(self, scored: ScoredReading) -> None: ...

    async def history(self, device_id: DeviceId, *, limit: int) -> list[ScoredReading]:
        """Return the most recent `limit` readings, oldest first."""
        ...


class DeviceSnapshot(Protocol):
    """Latest known reading per device. Lossy by design and cheap to read."""

    async def remember(self, scored: ScoredReading) -> None: ...

    async def latest(self) -> list[ScoredReading]: ...


class TelemetryStream(Protocol):
    """Live fan-out to every connected dashboard."""

    async def publish(self, scored: ScoredReading) -> None: ...

    def subscribe(self) -> AsyncIterator[ScoredReading]:
        """Yield readings as they arrive, until the consumer stops iterating."""
        ...
