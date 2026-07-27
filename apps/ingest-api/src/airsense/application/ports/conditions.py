"""Port for per-device rule state."""

from typing import Protocol

from airsense.domain.conditions import ConditionState
from airsense.domain.telemetry import DeviceId


class ConditionStore(Protocol):
    """Holds the debounce history and current condition for each device.

    Kept out of process memory deliberately: this is what decides whether a
    ticket opens, and losing it on restart would let a device that has been
    alerting for an hour start again from NORMAL.
    """

    async def load(self, device_id: DeviceId) -> ConditionState: ...

    async def save(self, device_id: DeviceId, state: ConditionState) -> None: ...
