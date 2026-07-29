"""Replay the committed telemetry fixture to MQTT, one topic per device.

Two regimes. By default every device ping-pongs through the *healthy* prefix of
its trajectory, so an idle fleet stays quiet and nothing alerts on its own. A
fault injection releases one device to run forward through the degradation ramp
to failure, and hold there.

Ping-pong rather than looping back to frame zero: wrapping would step the
channels discontinuously, and the model's delta features are computed across
exactly that step.
"""

import asyncio
import json
from collections.abc import Awaitable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Protocol

import aiomqtt
import pandas as pd
import structlog

log = structlog.get_logger("replay")

CHANNEL_COLUMNS: Final[list[str]] = [
    "compressor_current_a",
    "discharge_pressure_kpa",
    "suction_temperature_c",
    "ambient_temperature_c",
    "vibration_rms_mm_s",
]

ChannelRow = dict[str, float]


class MessagePublisher(Protocol):
    """The slice of an MQTT client a tick needs. Keeps `_tick` testable.

    Declared as returning an awaitable rather than as `async def`: that form
    accepts both coroutine functions and anything else awaitable, which is what
    lets the real aiomqtt client and the test double both satisfy it.
    """

    def publish(self, topic: str, payload: str, qos: int = 0) -> Awaitable[None]: ...


@dataclass(frozen=True, slots=True)
class Trajectory:
    """One device's frames, with the two positions the demo cares about.

    `healthy_frames` bounds the idle ping-pong. `ramp_start` is where injection
    begins, and sits deliberately later: starting the ramp at the healthy
    boundary is faithful but slow, because the model needs most of the ramp
    before the score clears the alert threshold. Measured across all four
    devices, entering at the healthy boundary reaches ALERT in 49-56 samples
    against 33-38 from `ramp_start`.
    """

    frames: list[ChannelRow]
    healthy_frames: int
    ramp_start: int

    def __post_init__(self) -> None:
        if not self.frames:
            raise ValueError("a trajectory needs at least one frame")
        if not 1 <= self.healthy_frames <= len(self.frames):
            raise ValueError("healthy_frames must index into frames")
        if not self.healthy_frames <= self.ramp_start < len(self.frames):
            raise ValueError("ramp_start must sit at or after the healthy prefix")


def load_trajectories(
    path: Path, *, healthy_ceiling: float, injection_start: float
) -> dict[str, Trajectory]:
    """Read the fixture, marking each device's idle span and injection point."""
    if not healthy_ceiling < injection_start < 1.0:
        raise ValueError("expected healthy_ceiling < injection_start < 1.0")

    frame = pd.read_parquet(path).sort_values(["device_id", "sequence"])
    trajectories: dict[str, Trajectory] = {}
    for device_id, group in frame.groupby("device_id"):
        rows = group[CHANNEL_COLUMNS].to_numpy(dtype=float).tolist()
        healthy = max(int((group["life_fraction"] <= healthy_ceiling).sum()), 2)
        ramp = max(int((group["life_fraction"] <= injection_start).sum()), healthy)
        trajectories[str(device_id)] = Trajectory(
            frames=[dict(zip(CHANNEL_COLUMNS, row, strict=True)) for row in rows],
            healthy_frames=healthy,
            ramp_start=min(ramp, len(rows) - 1),
        )
    return trajectories


@dataclass(slots=True)
class ReplayEngine:
    trajectories: dict[str, Trajectory]
    host: str
    port: int
    topic_prefix: str
    client_id: str
    interval_seconds: float
    reconnect_seconds: float = 3.0
    _sequence: dict[str, int] = field(init=False)
    _position: dict[str, int] = field(init=False)
    _faulted: set[str] = field(init=False)

    def __post_init__(self) -> None:
        self._sequence = dict.fromkeys(self.trajectories, 0)
        self._position = dict.fromkeys(self.trajectories, 0)
        self._faulted = set()

    @property
    def device_ids(self) -> list[str]:
        return sorted(self.trajectories)

    def is_faulted(self, device_id: str) -> bool:
        return device_id in self._faulted

    def inject_fault(self, device_id: str) -> None:
        """Release a device into its degradation ramp.

        Enters partway along the ramp rather than jumping to failure: the
        scorer's features include a window mean and a delta, and a
        discontinuous jump to the end produces a feature vector unlike anything
        in the training set.
        """
        if device_id not in self.trajectories:
            raise KeyError(device_id)
        self._faulted.add(device_id)
        self._position[device_id] = self.trajectories[device_id].ramp_start

    def reset(self, device_id: str) -> None:
        self._faulted.discard(device_id)
        self._position[device_id] = 0

    def reset_all(self) -> None:
        for device_id in self.trajectories:
            self.reset(device_id)

    def _next_frame(self, device_id: str) -> ChannelRow:
        trajectory = self.trajectories[device_id]
        position = self._position[device_id]

        if device_id in self._faulted:
            # Hold at failure so the alert and its ticket persist for as long as
            # anyone is looking at them.
            self._position[device_id] = min(position + 1, len(trajectory.frames) - 1)
            return trajectory.frames[position]

        span = trajectory.healthy_frames
        cycle = 2 * span - 2
        offset = position % cycle if cycle else 0
        self._position[device_id] = position + 1
        return trajectory.frames[offset if offset < span else cycle - offset]

    async def run(self) -> None:
        """Publish until cancelled, reconnecting whenever the broker drops."""
        while True:
            try:
                async with aiomqtt.Client(
                    hostname=self.host, port=self.port, identifier=self.client_id
                ) as client:
                    log.info(
                        "replay.started",
                        devices=len(self.trajectories),
                        interval=self.interval_seconds,
                    )
                    while True:
                        await self._tick(client)
                        await asyncio.sleep(self.interval_seconds)
            except aiomqtt.MqttError as exc:
                log.warning("replay.disconnected", error=str(exc))
                await asyncio.sleep(self.reconnect_seconds)

    async def _tick(self, client: MessagePublisher) -> None:
        # One timestamp for the whole tick so the dashboard's x-axis lines up
        # across devices instead of fanning out by however long publishing took.
        recorded_at = datetime.now(UTC).isoformat()
        for device_id in self.device_ids:
            sequence = self._sequence[device_id]
            self._sequence[device_id] = sequence + 1

            payload = {
                "device_id": device_id,
                "recorded_at": recorded_at,
                "sequence": sequence,
                **self._next_frame(device_id),
            }
            await client.publish(f"{self.topic_prefix}/{device_id}", json.dumps(payload), qos=1)
