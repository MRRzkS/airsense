"""The single wire representation of a reading.

MQTT payloads, Redis pub/sub frames and SSE events all use this shape, so there
is one parser and one serializer rather than three that can drift apart.
"""

from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict

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

    @classmethod
    def from_domain(cls, reading: SensorReading) -> Self:
        return cls(
            device_id=reading.device_id.value,
            recorded_at=reading.recorded_at,
            sequence=reading.sequence,
            compressor_current_a=reading.compressor_current_a,
            discharge_pressure_kpa=reading.discharge_pressure_kpa,
            suction_temperature_c=reading.suction_temperature_c,
            ambient_temperature_c=reading.ambient_temperature_c,
            vibration_rms_mm_s=reading.vibration_rms_mm_s,
        )
