"""Redis adapter satisfying both `DeviceSnapshot` and `TelemetryStream`.

One connection, two ports: the latest-state hash and the pub/sub channel are
different access patterns over the same data, and splitting them across two
adapters would buy nothing.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Final

from redis.asyncio import Redis

from airsense.domain.telemetry import SensorReading
from airsense.infrastructure.wire import TelemetryMessage

SNAPSHOT_KEY: Final = "airsense:latest"
STREAM_CHANNEL: Final = "airsense:telemetry"


def create_client(dsn: str) -> Redis:
    return Redis.from_url(dsn, decode_responses=True)


@dataclass(frozen=True, slots=True)
class RedisTelemetryHub:
    client: Redis

    async def remember(self, reading: SensorReading) -> None:
        payload = TelemetryMessage.from_domain(reading).model_dump_json()
        await self.client.hset(SNAPSHOT_KEY, reading.device_id.value, payload)

    async def latest(self) -> list[SensorReading]:
        # decode_responses is a runtime flag the redis stubs cannot see, so the
        # declared type stays the union. Pydantic parses either representation.
        raw: dict[str | bytes, str | bytes] = await self.client.hgetall(SNAPSHOT_KEY)
        return [TelemetryMessage.model_validate_json(value).to_domain() for value in raw.values()]

    async def publish(self, reading: SensorReading) -> None:
        payload = TelemetryMessage.from_domain(reading).model_dump_json()
        await self.client.publish(STREAM_CHANNEL, payload)

    async def subscribe(self) -> AsyncIterator[SensorReading]:
        async with self.client.pubsub() as pubsub:
            await pubsub.subscribe(STREAM_CHANNEL)
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                yield TelemetryMessage.model_validate_json(message["data"]).to_domain()
