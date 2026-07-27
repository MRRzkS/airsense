"""The CRM panel's read endpoint."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel

from airsense.api.deps import ServicesDep
from airsense.domain.ticketing import Ticket

router = APIRouter(prefix="/tickets", tags=["tickets"])


class TicketResponse(BaseModel):
    ticket_id: str
    device_id: str
    fault_class: str
    diagnostic_code: str
    severity: str
    status: str
    opened_at: datetime
    updated_at: datetime
    closed_at: datetime | None

    @classmethod
    def of(cls, ticket: Ticket) -> "TicketResponse":
        return cls(
            ticket_id=ticket.ticket_id,
            device_id=ticket.device_id.value,
            fault_class=ticket.fault_class.value,
            diagnostic_code=ticket.diagnostic_code,
            severity=ticket.severity.value,
            status=ticket.status.value,
            opened_at=ticket.opened_at,
            updated_at=ticket.updated_at,
            closed_at=ticket.closed_at,
        )


@router.get("", summary="Support tickets, newest first")
async def list_tickets(
    services: ServicesDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[TicketResponse]:
    tickets = await services.list_tickets(limit=limit)
    return [TicketResponse.of(ticket) for ticket in tickets]
