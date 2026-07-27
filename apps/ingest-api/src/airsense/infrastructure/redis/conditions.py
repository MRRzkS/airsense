"""Redis-backed `ConditionStore`.

Durable rather than in-process because this state decides whether a ticket
opens. Losing it on deploy would reset an alerting device to NORMAL and let the
rules re-open a ticket the CRM already has.
"""

import json
from dataclasses import dataclass
from typing import Final

from redis.asyncio import Redis

from airsense.domain.conditions import ConditionState, DeviceCondition
from airsense.domain.telemetry import DeviceId

CONDITION_KEY: Final = "airsense:conditions"


@dataclass(frozen=True, slots=True)
class RedisConditionStore:
    client: Redis

    async def load(self, device_id: DeviceId) -> ConditionState:
        raw = await self.client.hget(CONDITION_KEY, device_id.value)
        if raw is None:
            return ConditionState()
        payload = json.loads(raw)
        return ConditionState(
            condition=DeviceCondition(payload["condition"]),
            recent_scores=tuple(payload["recent_scores"]),
        )

    async def save(self, device_id: DeviceId, state: ConditionState) -> None:
        payload = json.dumps(
            {
                "condition": state.condition.value,
                "recent_scores": list(state.recent_scores),
            }
        )
        await self.client.hset(CONDITION_KEY, device_id.value, payload)
