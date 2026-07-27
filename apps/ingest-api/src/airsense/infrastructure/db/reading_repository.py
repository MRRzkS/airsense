"""TimescaleDB-backed implementation of `ReadingRepository`."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from airsense.domain.conditions import DeviceCondition
from airsense.domain.scoring import ScoredReading
from airsense.domain.telemetry import Channel, DeviceId, SensorReading
from airsense.infrastructure.db.models import ReadingRow


def _to_domain(row: ReadingRow) -> ScoredReading:
    reading = SensorReading.from_channels(
        device_id=DeviceId(row.device_id),
        recorded_at=row.recorded_at,
        sequence=row.sequence,
        channels={
            Channel.COMPRESSOR_CURRENT: row.compressor_current_a,
            Channel.DISCHARGE_PRESSURE: row.discharge_pressure_kpa,
            Channel.SUCTION_TEMPERATURE: row.suction_temperature_c,
            Channel.AMBIENT_TEMPERATURE: row.ambient_temperature_c,
            Channel.VIBRATION_RMS: row.vibration_rms_mm_s,
        },
    )
    return ScoredReading(
        reading=reading,
        health_index=row.health_index,
        condition=DeviceCondition(row.condition),
    )


@dataclass(frozen=True, slots=True)
class TimescaleReadingRepository:
    sessions: async_sessionmaker[AsyncSession]

    async def append(self, scored: ScoredReading) -> None:
        reading = scored.reading
        # A device that reconnects replays its last frame, and MQTT QoS 1 is
        # at-least-once. Ingest is therefore idempotent on the primary key
        # instead of treating a duplicate as an error.
        statement = (
            insert(ReadingRow)
            .values(
                recorded_at=reading.recorded_at,
                device_id=reading.device_id.value,
                sequence=reading.sequence,
                health_index=scored.health_index,
                condition=scored.condition.value,
                compressor_current_a=reading.compressor_current_a,
                discharge_pressure_kpa=reading.discharge_pressure_kpa,
                suction_temperature_c=reading.suction_temperature_c,
                ambient_temperature_c=reading.ambient_temperature_c,
                vibration_rms_mm_s=reading.vibration_rms_mm_s,
            )
            .on_conflict_do_nothing(index_elements=["recorded_at", "device_id"])
        )
        async with self.sessions.begin() as session:
            await session.execute(statement)

    async def history(self, device_id: DeviceId, *, limit: int) -> list[ScoredReading]:
        statement = (
            select(ReadingRow)
            .where(ReadingRow.device_id == device_id.value)
            .order_by(ReadingRow.recorded_at.desc())
            .limit(limit)
        )
        async with self.sessions() as session:
            rows = list((await session.scalars(statement)).all())
        return [_to_domain(row) for row in reversed(rows)]
