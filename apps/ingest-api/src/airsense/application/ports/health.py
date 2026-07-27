"""Port for reporting downstream dependency reachability."""

from typing import Protocol


class DependencyHealth(Protocol):
    async def check(self) -> dict[str, str]:
        """Map each dependency name to "ok" or a short failure reason.

        Implementations must not raise: a readiness probe that fails to answer
        tells an orchestrator less than one that names the broken dependency.
        """
        ...
