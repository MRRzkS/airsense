"""A reading paired with what the model and the rules made of it."""

from dataclasses import dataclass

from airsense.domain.conditions import DeviceCondition
from airsense.domain.telemetry import SensorReading


@dataclass(frozen=True, slots=True)
class ScoredReading:
    """One reading, its degradation score, and the device's condition.

    `health_index` is a fraction in [0, 1]: 0.0 for a unit that looks healthy,
    1.0 at the modelled point of failure. It is `None` while a device is still
    filling its first feature window — an unscored reading is honest, a
    defaulted zero would be a lie the rules engine would act on.

    `condition` is the debounced state from `ConditionPolicy`, not a direct
    reading of the score. A device sitting above the alert threshold for one
    sample is still NORMAL.
    """

    reading: SensorReading
    health_index: float | None
    condition: DeviceCondition = DeviceCondition.NORMAL

    def __post_init__(self) -> None:
        if self.health_index is None:
            return
        if not 0.0 <= self.health_index <= 1.0:
            raise ValueError(f"health_index out of range: {self.health_index}")

    @property
    def is_scored(self) -> bool:
        return self.health_index is not None
