"""Ticket sink selection.

The whole point of the `TicketSink` port: which CRM the system writes to is a
startup configuration value, and nothing upstream of this function changes when
it flips.
"""

from airsense.application.ports.ticketing import TicketSink
from airsense.infrastructure.config import Settings
from airsense.infrastructure.crm.memory import InMemoryTicketSink


def create_ticket_sink(settings: Settings) -> TicketSink:
    if settings.ticket_sink == "hubspot":
        raise NotImplementedError(
            "TICKET_SINK=hubspot is not wired yet; the HubSpot adapter lands in P4"
        )
    return InMemoryTicketSink()
