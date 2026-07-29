"""Contract tests for the HubSpot adapter.

Every request and response here is mocked. This proves the adapter builds the
requests HubSpot's documentation describes and parses the shapes it documents —
it does **not** prove HubSpot accepts them. No live call has ever been made.
"""

import json
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
import respx

from airsense.domain.severity import Severity
from airsense.domain.telemetry import DeviceId
from airsense.domain.ticketing import FaultClass, TicketStatus
from airsense.infrastructure.config import Settings
from airsense.infrastructure.crm.factory import create_ticket_sink
from airsense.infrastructure.crm.hubspot import (
    BASE_URL,
    DEVICE_PROPERTY,
    FAULT_PROPERTY,
    SEVERITY_PROPERTY,
    HubSpotTicketSink,
)
from airsense.infrastructure.crm.memory import InMemoryTicketSink

NOW = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)
DEVICE = DeviceId("AC-0001")
FAULT = FaultClass.COMPRESSOR_DEGRADATION
OPEN_STAGE, CLOSED_STAGE = "1", "4"


def ticket_payload(stage: str = OPEN_STAGE, **overrides: Any) -> dict[str, Any]:
    properties = {
        "hs_object_id": "551",
        "hs_pipeline_stage": stage,
        "hs_ticket_priority": "HIGH",
        "createdate": "2026-07-27T11:00:00Z",
        "hs_lastmodifieddate": "2026-07-27T11:30:00Z",
        "closed_date": "2026-07-27T11:45:00Z" if stage == CLOSED_STAGE else None,
        DEVICE_PROPERTY: "AC-0001",
        FAULT_PROPERTY: FAULT.value,
        SEVERITY_PROPERTY: "HIGH",
        **overrides,
    }
    return {"id": "551", "properties": properties}


def sent_properties(route: respx.Route) -> dict[str, Any]:
    """The property bag of the last request, parsed rather than string-matched."""
    body: dict[str, Any] = json.loads(route.calls.last.request.read())
    return dict(body["properties"])


@pytest.fixture
def sink() -> HubSpotTicketSink:
    return HubSpotTicketSink(
        client=httpx.AsyncClient(base_url=BASE_URL, headers={"Authorization": "Bearer t"}),
        pipeline="0",
        open_stage=OPEN_STAGE,
        closed_stage=CLOSED_STAGE,
    )


# ─── Selection ────────────────────────────────────────────────────────────


def test_the_default_sink_is_in_memory() -> None:
    settings = Settings(
        database_dsn="postgresql+asyncpg://a:b@h/d", redis_dsn="redis://h", mqtt_host="h"
    )

    assert isinstance(create_ticket_sink(settings), InMemoryTicketSink)


def test_selecting_hubspot_without_a_token_fails_at_startup() -> None:
    # Better than discovering it when the first ticket is dropped on the floor.
    settings = Settings(
        database_dsn="postgresql+asyncpg://a:b@h/d",
        redis_dsn="redis://h",
        mqtt_host="h",
        ticket_sink="hubspot",
    )

    with pytest.raises(ValueError, match="HUBSPOT_ACCESS_TOKEN"):
        create_ticket_sink(settings)


def test_selecting_hubspot_with_a_token_builds_the_hubspot_sink() -> None:
    settings = Settings(
        database_dsn="postgresql+asyncpg://a:b@h/d",
        redis_dsn="redis://h",
        mqtt_host="h",
        ticket_sink="hubspot",
        hubspot_access_token="pat-na1-secret",
    )

    assert isinstance(create_ticket_sink(settings), HubSpotTicketSink)


# ─── Opening ──────────────────────────────────────────────────────────────


@respx.mock
async def test_open_posts_the_documented_property_bag(sink: HubSpotTicketSink) -> None:
    route = respx.post(f"{BASE_URL}/crm/v3/objects/tickets").mock(
        return_value=httpx.Response(201, json=ticket_payload())
    )

    ticket = await sink.open(DEVICE, FAULT, Severity.HIGH, NOW)

    properties = sent_properties(route)
    assert properties["hs_pipeline_stage"] == OPEN_STAGE
    assert properties["hs_pipeline"] == "0"
    assert properties[DEVICE_PROPERTY] == "AC-0001"
    assert properties[FAULT_PROPERTY] == FAULT.value
    assert ticket.ticket_id == "551"
    assert ticket.status is TicketStatus.OPEN


@respx.mock
async def test_the_diagnostic_code_reaches_the_subject_line(sink: HubSpotTicketSink) -> None:
    # A technician reading the CRM should see the service code without opening
    # the ticket body.
    route = respx.post(f"{BASE_URL}/crm/v3/objects/tickets").mock(
        return_value=httpx.Response(201, json=ticket_payload())
    )

    await sink.open(DEVICE, FAULT, Severity.MEDIUM, NOW)

    assert "F1-07" in sent_properties(route)["subject"]


@respx.mock
async def test_critical_maps_onto_hubspots_highest_priority(sink: HubSpotTicketSink) -> None:
    # HubSpot's stock vocabulary has no CRITICAL, so the exact severity is kept
    # in a custom property rather than silently lost.
    route = respx.post(f"{BASE_URL}/crm/v3/objects/tickets").mock(
        return_value=httpx.Response(201, json=ticket_payload())
    )

    await sink.open(DEVICE, FAULT, Severity.CRITICAL, NOW)
    properties = sent_properties(route)

    assert properties["hs_ticket_priority"] == "HIGH"
    assert properties[SEVERITY_PROPERTY] == "CRITICAL"


@respx.mock
async def test_an_api_error_is_not_swallowed(sink: HubSpotTicketSink) -> None:
    respx.post(f"{BASE_URL}/crm/v3/objects/tickets").mock(
        return_value=httpx.Response(403, json={"message": "missing scope"})
    )

    with pytest.raises(httpx.HTTPStatusError):
        await sink.open(DEVICE, FAULT, Severity.LOW, NOW)


# ─── Lookup ───────────────────────────────────────────────────────────────


@respx.mock
async def test_lookup_filters_on_device_and_fault_class(sink: HubSpotTicketSink) -> None:
    route = respx.post(f"{BASE_URL}/crm/v3/objects/tickets/search").mock(
        return_value=httpx.Response(200, json={"results": [ticket_payload()]})
    )

    ticket = await sink.latest_for(DEVICE, FAULT)

    filters = json.loads(route.calls.last.request.read())["filterGroups"][0]["filters"]
    assert {f["propertyName"]: f["value"] for f in filters} == {
        DEVICE_PROPERTY: "AC-0001",
        FAULT_PROPERTY: FAULT.value,
    }
    assert ticket is not None
    assert ticket.device_id == DEVICE


@respx.mock
async def test_lookup_returns_none_when_nothing_matches(sink: HubSpotTicketSink) -> None:
    respx.post(f"{BASE_URL}/crm/v3/objects/tickets/search").mock(
        return_value=httpx.Response(200, json={"results": []})
    )

    assert await sink.latest_for(DEVICE, FAULT) is None


@respx.mock
async def test_a_closed_ticket_parses_with_its_closing_time(sink: HubSpotTicketSink) -> None:
    # The cooldown rule needs this; a closed ticket without a timestamp would
    # violate the domain invariant on construction.
    respx.post(f"{BASE_URL}/crm/v3/objects/tickets/search").mock(
        return_value=httpx.Response(200, json={"results": [ticket_payload(stage=CLOSED_STAGE)]})
    )

    ticket = await sink.latest_for(DEVICE, FAULT)

    assert ticket is not None
    assert ticket.status is TicketStatus.CLOSED
    assert ticket.closed_at == datetime(2026, 7, 27, 11, 45, tzinfo=UTC)


@respx.mock
async def test_a_closed_ticket_missing_closed_date_still_parses(sink: HubSpotTicketSink) -> None:
    # HubSpot only populates closed_date in some configurations; falling back to
    # the modification time keeps the cooldown measurable.
    respx.post(f"{BASE_URL}/crm/v3/objects/tickets/search").mock(
        return_value=httpx.Response(
            200, json={"results": [ticket_payload(stage=CLOSED_STAGE, closed_date=None)]}
        )
    )

    ticket = await sink.latest_for(DEVICE, FAULT)

    assert ticket is not None
    assert ticket.closed_at == datetime(2026, 7, 27, 11, 30, tzinfo=UTC)


# ─── Updates ──────────────────────────────────────────────────────────────


@respx.mock
async def test_escalation_patches_rather_than_creating(sink: HubSpotTicketSink) -> None:
    # Rule 2 lives or dies on this: a POST here would duplicate the ticket.
    route = respx.patch(f"{BASE_URL}/crm/v3/objects/tickets/551").mock(
        return_value=httpx.Response(200, json=ticket_payload())
    )

    await sink.escalate("551", Severity.CRITICAL, NOW)

    assert route.called
    assert sent_properties(route)[SEVERITY_PROPERTY] == "CRITICAL"


@respx.mock
async def test_resolving_moves_the_ticket_to_the_closed_stage(sink: HubSpotTicketSink) -> None:
    route = respx.patch(f"{BASE_URL}/crm/v3/objects/tickets/551").mock(
        return_value=httpx.Response(200, json=ticket_payload(stage=CLOSED_STAGE))
    )

    ticket = await sink.resolve("551", NOW)

    assert sent_properties(route)["hs_pipeline_stage"] == CLOSED_STAGE
    assert ticket.status is TicketStatus.CLOSED


@respx.mock
async def test_listing_requests_the_properties_the_panel_renders(
    sink: HubSpotTicketSink,
) -> None:
    route = respx.get(f"{BASE_URL}/crm/v3/objects/tickets").mock(
        return_value=httpx.Response(200, json={"results": [ticket_payload()]})
    )

    tickets = await sink.list_recent(limit=5)

    assert DEVICE_PROPERTY in str(route.calls.last.request.url)
    assert len(tickets) == 1
