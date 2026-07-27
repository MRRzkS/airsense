"""Port for degradation scoring."""

from typing import Protocol

from airsense.domain.telemetry import SensorReading


class DegradationScorer(Protocol):
    def score(self, reading: SensorReading) -> float | None:
        """Return the device's health index in [0, 1], or None if not yet scorable.

        Stateful by contract: implementations accumulate a per-device window and
        return None until it is full. Callers must submit every reading, in
        order, exactly once.
        """
        ...
