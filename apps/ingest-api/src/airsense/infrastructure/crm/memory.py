"""In-memory ticket sink backing the CRM panel this application serves.

The live demo runs on this by design: it has no external dependency, so the one
thing a reviewer is asked to watch cannot fail because someone else's API is
having a bad afternoon. Swapping to HubSpot is an environment variable.
"""

import itertools
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from datetime import datetime

from prometheus_client import Counter

from airsense.domain.severity import Severity
from airsense.domain.telemetry import DeviceId
from airsense.domain.ticketing import FaultClass, Ticket, TicketStatus

TICKETS_OPENED = Counter("airsense_tickets_opened_total", "Support tickets opened")
TICKETS_ESCALATED = Counter("airsense_tickets_escalated_total", "Support tickets escalated")
TICKETS_RESOLVED = Counter("airsense_tickets_resolved_total", "Support tickets resolved")


class TicketNotFoundError(KeyError):
    """Raised when an operation names a ticket that does not exist."""


@dataclass(slots=True)
class InMemoryTicketSink:
    tickets: dict[str, Ticket] = field(default_factory=dict)
    # Iterator[int] rather than itertools.count[int]: the concrete class only
    # became subscriptable at runtime in 3.13, and this project targets 3.12.
    # An iterator of ints is all this needs anyway — it is only ever advanced.
    _sequence: Iterator[int] = field(default_factory=lambda: itertools.count(1))

    async def latest_for(self, device_id: DeviceId, fault_class: FaultClass) -> Ticket | None:
        matching = [
            ticket
            for ticket in self.tickets.values()
            if ticket.device_id == device_id and ticket.fault_class is fault_class
        ]
        if not matching:
            return None
        return max(matching, key=lambda ticket: ticket.opened_at)

    async def open(
        self,
        device_id: DeviceId,
        fault_class: FaultClass,
        severity: Severity,
        at: datetime,
    ) -> Ticket:
        ticket = Ticket(
            ticket_id=f"AS-{next(self._sequence):04d}",
            device_id=device_id,
            fault_class=fault_class,
            severity=severity,
            status=TicketStatus.OPEN,
            opened_at=at,
            updated_at=at,
        )
        self.tickets[ticket.ticket_id] = ticket
        TICKETS_OPENED.inc()
        return ticket

    async def escalate(self, ticket_id: str, severity: Severity, at: datetime) -> Ticket:
        ticket = replace(self._get(ticket_id), severity=severity, updated_at=at)
        self.tickets[ticket_id] = ticket
        TICKETS_ESCALATED.inc()
        return ticket

    async def resolve(self, ticket_id: str, at: datetime) -> Ticket:
        ticket = replace(
            self._get(ticket_id),
            status=TicketStatus.CLOSED,
            updated_at=at,
            closed_at=at,
        )
        self.tickets[ticket_id] = ticket
        TICKETS_RESOLVED.inc()
        return ticket

    async def list_recent(self, *, limit: int) -> list[Ticket]:
        ordered = sorted(self.tickets.values(), key=lambda t: t.updated_at, reverse=True)
        return ordered[:limit]

    def _get(self, ticket_id: str) -> Ticket:
        try:
            return self.tickets[ticket_id]
        except KeyError as exc:
            raise TicketNotFoundError(ticket_id) from exc
