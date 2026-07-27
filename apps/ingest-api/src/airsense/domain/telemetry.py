"""Telemetry value objects shared by every layer.

Stdlib only. These types carry the physical invariants of a residential split
air conditioner and nothing else — no serialization, no persistence concerns.
"""

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final, Self

DEVICE_ID_PATTERN: Final = re.compile(r"^AC-\d{4}$")


class Channel(StrEnum):
    """The five sensors a connected split unit reports."""

    COMPRESSOR_CURRENT = "compressor_current_a"
    DISCHARGE_PRESSURE = "discharge_pressure_kpa"
    SUCTION_TEMPERATURE = "suction_temperature_c"
    AMBIENT_TEMPERATURE = "ambient_temperature_c"
    VIBRATION_RMS = "vibration_rms_mm_s"


# Envelopes for a ~3.5 kW residential split unit in cooling mode. A value
# outside these bounds is a sensor or transport fault rather than a reading:
# no real unit draws 400 A, and a suction line at 200 C is a decode error.
# Deliberately wide — this rejects nonsense, it does not detect degradation.
PLAUSIBLE_RANGE: Final[dict[Channel, tuple[float, float]]] = {
    Channel.COMPRESSOR_CURRENT: (0.0, 40.0),
    Channel.DISCHARGE_PRESSURE: (400.0, 5000.0),
    Channel.SUCTION_TEMPERATURE: (-20.0, 60.0),
    Channel.AMBIENT_TEMPERATURE: (-30.0, 60.0),
    Channel.VIBRATION_RMS: (0.0, 50.0),
}


class ImplausibleReadingError(ValueError):
    """Raised when a reading violates a physical invariant."""


@dataclass(frozen=True, slots=True)
class DeviceId:
    """Identifier for one installed unit, formatted `AC-0001`."""

    value: str

    def __post_init__(self) -> None:
        if not DEVICE_ID_PATTERN.match(self.value):
            raise ValueError(f"malformed device id: {self.value!r}")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class SensorReading:
    """One timestamped sample from one unit.

    Invariants, enforced at construction:
      - `recorded_at` is timezone-aware; naive timestamps are ambiguous across
        the fleet's installation sites and are rejected outright.
      - `sequence` is non-negative and monotonic per device (ordering is the
        caller's responsibility; this only rejects negatives).
      - every channel falls inside `PLAUSIBLE_RANGE`.
    """

    device_id: DeviceId
    recorded_at: datetime
    sequence: int
    compressor_current_a: float
    discharge_pressure_kpa: float
    suction_temperature_c: float
    ambient_temperature_c: float
    vibration_rms_mm_s: float

    def __post_init__(self) -> None:
        if self.recorded_at.tzinfo is None:
            raise ImplausibleReadingError("recorded_at must be timezone-aware")
        if self.sequence < 0:
            raise ImplausibleReadingError(f"negative sequence: {self.sequence}")

        for channel, value in self.channels.items():
            low, high = PLAUSIBLE_RANGE[channel]
            if not low <= value <= high:
                raise ImplausibleReadingError(
                    f"{channel.value}={value} outside plausible range [{low}, {high}]"
                )

    @property
    def channels(self) -> dict[Channel, float]:
        return {
            Channel.COMPRESSOR_CURRENT: self.compressor_current_a,
            Channel.DISCHARGE_PRESSURE: self.discharge_pressure_kpa,
            Channel.SUCTION_TEMPERATURE: self.suction_temperature_c,
            Channel.AMBIENT_TEMPERATURE: self.ambient_temperature_c,
            Channel.VIBRATION_RMS: self.vibration_rms_mm_s,
        }

    @classmethod
    def from_channels(
        cls,
        *,
        device_id: DeviceId,
        recorded_at: datetime,
        sequence: int,
        channels: dict[Channel, float],
    ) -> Self:
        missing = set(Channel) - channels.keys()
        if missing:
            raise ImplausibleReadingError(
                "missing channels: " + ", ".join(sorted(c.value for c in missing))
            )
        return cls(
            device_id=device_id,
            recorded_at=recorded_at,
            sequence=sequence,
            compressor_current_a=channels[Channel.COMPRESSOR_CURRENT],
            discharge_pressure_kpa=channels[Channel.DISCHARGE_PRESSURE],
            suction_temperature_c=channels[Channel.SUCTION_TEMPERATURE],
            ambient_temperature_c=channels[Channel.AMBIENT_TEMPERATURE],
            vibration_rms_mm_s=channels[Channel.VIBRATION_RMS],
        )
