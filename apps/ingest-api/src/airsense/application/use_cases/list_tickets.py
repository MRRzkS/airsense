"""Read-side use case backing the CRM panel."""

from dataclasses import dataclass

from airsense.application.ports.ticketing import TicketSink
from airsense.domain.ticketing import Ticket


@dataclass(frozen=True, slots=True)
class ListTickets:
    sink: TicketSink

    async def __call__(self, *, limit: int) -> list[Ticket]:
        return await self.sink.list_recent(limit=limit)
