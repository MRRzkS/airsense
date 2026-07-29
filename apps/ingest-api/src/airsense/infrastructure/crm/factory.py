"""Ticket sink selection.

The whole point of the `TicketSink` port: which CRM the system writes to is a
startup configuration value, and nothing upstream of this function changes when
it flips.
"""

from airsense.application.ports.ticketing import TicketSink
from airsense.infrastructure.config import Settings
from airsense.infrastructure.crm.hubspot import HubSpotTicketSink
from airsense.infrastructure.crm.hubspot import create_client as create_hubspot_client
from airsense.infrastructure.crm.memory import InMemoryTicketSink


def create_ticket_sink(settings: Settings) -> TicketSink:
    if settings.ticket_sink != "hubspot":
        return InMemoryTicketSink()

    if not settings.hubspot_access_token:
        # Failing at startup beats discovering it when the first ticket is
        # dropped on the floor an hour into a demo.
        raise ValueError("TICKET_SINK=hubspot requires HUBSPOT_ACCESS_TOKEN")

    return HubSpotTicketSink(
        client=create_hubspot_client(settings.hubspot_access_token),
        pipeline=settings.hubspot_pipeline,
        open_stage=settings.hubspot_open_stage,
        closed_stage=settings.hubspot_closed_stage,
    )
