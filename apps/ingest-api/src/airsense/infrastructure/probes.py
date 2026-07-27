"""Dependency reachability checks behind `/ready`."""

from dataclasses import dataclass

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


@dataclass(frozen=True, slots=True)
class DependencyProbe:
    engine: AsyncEngine
    client: Redis

    async def check(self) -> dict[str, str]:
        """Report each dependency as "ok" or a short failure reason.

        Never raises: a readiness probe that 500s tells an orchestrator less
        than one that reports which dependency is down.
        """
        return {"database": await self._database(), "cache": await self._cache()}

    async def _database(self) -> str:
        try:
            async with self.engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        except Exception as exc:
            return type(exc).__name__
        return "ok"

    async def _cache(self) -> str:
        try:
            await self.client.ping()
        except Exception as exc:
            return type(exc).__name__
        return "ok"
