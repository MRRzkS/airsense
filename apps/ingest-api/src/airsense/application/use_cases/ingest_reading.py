"""Ingest one telemetry reading."""

from dataclasses import dataclass

from airsense.application.ports.scoring import DegradationScorer
from airsense.application.ports.telemetry import (
    DeviceSnapshot,
    ReadingRepository,
    TelemetryStream,
)
from airsense.domain.scoring import ScoredReading
from airsense.domain.telemetry import SensorReading


@dataclass(frozen=True, slots=True)
class IngestReading:
    """Score a reading, persist it, then cache it, then fan it out.

    The order is the contract. History is the only durable record, so it is
    written first: a dashboard that misses a frame recovers on the next one,
    whereas a reading dropped before persistence is gone. Cache and stream
    failures must therefore not prevent the write.

    Scoring happens before persistence so that history and the live stream
    always agree on a reading's score.
    """

    repository: ReadingRepository
    snapshot: DeviceSnapshot
    stream: TelemetryStream
    scorer: DegradationScorer

    async def __call__(self, reading: SensorReading) -> None:
        scored = ScoredReading(reading=reading, health_index=self.scorer.score(reading))

        await self.repository.append(scored)
        await self.snapshot.remember(scored)
        await self.stream.publish(scored)
