"""The CRM boundary.

This is the ports-and-adapters point of the project. `InMemoryTicketSink` backs
a CRM panel this application serves itself and is what the live demo uses, so
the demo cannot break on someone else's API. `HubSpotTicketSink` talks to the
real thing. Which one runs is a configuration value read at startup; no calling
code changes.
"""

from datetime import datetime
from typing import Protocol

from airsense.domain.severity import Severity
from airsense.domain.telemetry import DeviceId
from airsense.domain.ticketing import FaultClass, Ticket


class TicketSink(Protocol):
    """Somewhere support tickets live."""

    async def latest_for(self, device_id: DeviceId, fault_class: FaultClass) -> Ticket | None:
        """Return the most recent ticket for this pair, open or closed.

        Closed tickets must be returned too: the cooldown rule needs to know
        when the last one closed.
        """
        ...

    async def open(
        self,
        device_id: DeviceId,
        fault_class: FaultClass,
        severity: Severity,
        at: datetime,
    ) -> Ticket: ...

    async def escalate(self, ticket_id: str, severity: Severity, at: datetime) -> Ticket: ...

    async def resolve(self, ticket_id: str, at: datetime) -> Ticket: ...

    async def list_recent(self, *, limit: int) -> list[Ticket]:
        """Newest first. Backs the CRM panel."""
        ...
