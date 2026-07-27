"""Replay the committed telemetry fixture to MQTT, one topic per device."""

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


def load_tracks(path: Path) -> dict[str, list[ChannelRow]]:
    """Read the fixture into per-device frame lists, oldest first."""
    frame = pd.read_parquet(path).sort_values(["device_id", "sequence"])
    tracks: dict[str, list[ChannelRow]] = {}
    for device_id, group in frame.groupby("device_id"):
        rows = group[CHANNEL_COLUMNS].to_numpy(dtype=float).tolist()
        tracks[str(device_id)] = [dict(zip(CHANNEL_COLUMNS, row, strict=True)) for row in rows]
    return tracks


@dataclass(slots=True)
class ReplayEngine:
    """Publishes one frame per device per tick, looping at end of trajectory."""

    tracks: dict[str, list[ChannelRow]]
    host: str
    port: int
    topic_prefix: str
    client_id: str
    interval_seconds: float
    reconnect_seconds: float = 3.0
    _cursor: dict[str, int] = field(init=False)

    def __post_init__(self) -> None:
        self._cursor = dict.fromkeys(self.tracks, 0)

    @property
    def device_ids(self) -> list[str]:
        return sorted(self.tracks)

    async def run(self) -> None:
        """Publish until cancelled, reconnecting whenever the broker drops."""
        while True:
            try:
                async with aiomqtt.Client(
                    hostname=self.host, port=self.port, identifier=self.client_id
                ) as client:
                    log.info(
                        "replay.started",
                        devices=len(self.tracks),
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
            frames = self.tracks[device_id]
            index = self._cursor[device_id]
            self._cursor[device_id] = index + 1

            payload = {
                "device_id": device_id,
                "recorded_at": recorded_at,
                "sequence": index,
                **frames[index % len(frames)],
            }
            await client.publish(f"{self.topic_prefix}/{device_id}", json.dumps(payload), qos=1)
