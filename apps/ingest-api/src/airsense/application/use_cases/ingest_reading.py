"""Ingest one telemetry reading."""

from dataclasses import dataclass

from airsense.application.ports.scoring import DegradationScorer
from airsense.application.ports.telemetry import (
    DeviceSnapshot,
    ReadingRepository,
    TelemetryStream,
)
from airsense.application.use_cases.assess_degradation import AssessDegradation
from airsense.domain.scoring import ScoredReading
from airsense.domain.telemetry import SensorReading


@dataclass(frozen=True, slots=True)
class IngestReading:
    """Score a reading, assess it, persist it, cache it, then fan it out.

    The order is the contract. History is the only durable record, so it is
    written first: a dashboard that misses a frame recovers on the next one,
    whereas a reading dropped before persistence is gone. Cache and stream
    failures must therefore not prevent the write.

    Scoring and assessment happen before persistence so that history and the
    live stream always agree on a reading's score and condition.
    """

    repository: ReadingRepository
    snapshot: DeviceSnapshot
    stream: TelemetryStream
    scorer: DegradationScorer
    assess: AssessDegradation

    async def __call__(self, reading: SensorReading) -> None:
        health_index = self.scorer.score(reading)
        condition = await self.assess(reading.device_id, health_index, reading.recorded_at)
        scored = ScoredReading(reading=reading, health_index=health_index, condition=condition)

        await self.repository.append(scored)
        await self.snapshot.remember(scored)
        await self.stream.publish(scored)
