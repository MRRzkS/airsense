"""The single wire representation of a reading.

MQTT payloads, Redis pub/sub frames and SSE events all use this shape, so there
is one parser and one serializer rather than three that can drift apart.

`health_index` is absent inbound (devices do not score themselves) and present
outbound, which is why it is optional rather than two separate models.
"""

from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict

from airsense.domain.conditions import DeviceCondition
from airsense.domain.scoring import ScoredReading
from airsense.domain.telemetry import Channel, DeviceId, SensorReading


class TelemetryMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str
    recorded_at: datetime
    sequence: int
    compressor_current_a: float
    discharge_pressure_kpa: float
    suction_temperature_c: float
    ambient_temperature_c: float
    vibration_rms_mm_s: float
    health_index: float | None = None
    condition: DeviceCondition = DeviceCondition.NORMAL

    def to_domain(self) -> SensorReading:
        """Convert to the domain type, applying its physical invariants."""
        return SensorReading.from_channels(
            device_id=DeviceId(self.device_id),
            recorded_at=self.recorded_at,
            sequence=self.sequence,
            channels={
                Channel.COMPRESSOR_CURRENT: self.compressor_current_a,
                Channel.DISCHARGE_PRESSURE: self.discharge_pressure_kpa,
                Channel.SUCTION_TEMPERATURE: self.suction_temperature_c,
                Channel.AMBIENT_TEMPERATURE: self.ambient_temperature_c,
                Channel.VIBRATION_RMS: self.vibration_rms_mm_s,
            },
        )

    def to_scored(self) -> ScoredReading:
        return ScoredReading(
            reading=self.to_domain(),
            health_index=self.health_index,
            condition=self.condition,
        )

    @classmethod
    def from_scored(cls, scored: ScoredReading) -> Self:
        reading = scored.reading
        return cls(
            device_id=reading.device_id.value,
            recorded_at=reading.recorded_at,
            sequence=reading.sequence,
            compressor_current_a=reading.compressor_current_a,
            discharge_pressure_kpa=reading.discharge_pressure_kpa,
            suction_temperature_c=reading.suction_temperature_c,
            ambient_temperature_c=reading.ambient_temperature_c,
            vibration_rms_mm_s=reading.vibration_rms_mm_s,
            health_index=scored.health_index,
            condition=scored.condition,
        )
