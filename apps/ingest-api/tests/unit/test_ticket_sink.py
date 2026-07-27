"""The in-memory sink that backs the demo's CRM panel."""

from datetime import UTC, datetime, timedelta

import pytest

from airsense.domain.severity import Severity
from airsense.domain.telemetry import DeviceId
from airsense.domain.ticketing import FaultClass, TicketStatus
from airsense.infrastructure.crm.memory import InMemoryTicketSink, TicketNotFoundError

NOW = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)
DEVICE = DeviceId("AC-0001")
OTHER = DeviceId("AC-0002")
FAULT = FaultClass.COMPRESSOR_DEGRADATION


@pytest.fixture
def sink() -> InMemoryTicketSink:
    return InMemoryTicketSink()


async def test_nothing_is_found_before_anything_is_filed(sink: InMemoryTicketSink) -> None:
    assert await sink.latest_for(DEVICE, FAULT) is None


async def test_opening_yields_an_identifier_and_open_status(sink: InMemoryTicketSink) -> None:
    ticket = await sink.open(DEVICE, FAULT, Severity.HIGH, NOW)

    assert ticket.ticket_id
    assert ticket.status is TicketStatus.OPEN
    assert ticket.closed_at is None
    assert ticket.diagnostic_code == "F1-07"


async def test_identifiers_are_unique(sink: InMemoryTicketSink) -> None:
    first = await sink.open(DEVICE, FAULT, Severity.LOW, NOW)
    second = await sink.open(OTHER, FAULT, Severity.LOW, NOW)

    assert first.ticket_id != second.ticket_id


async def test_lookup_is_scoped_to_one_device(sink: InMemoryTicketSink) -> None:
    # The dedup key is (device, fault class). One device's open ticket must not
    # suppress another's.
    await sink.open(DEVICE, FAULT, Severity.LOW, NOW)

    assert await sink.latest_for(OTHER, FAULT) is None


async def test_lookup_returns_the_most_recent_including_closed(
    sink: InMemoryTicketSink,
) -> None:
    # The cooldown rule needs the closing time of the last ticket, so closed
    # ones cannot be hidden from this lookup.
    first = await sink.open(DEVICE, FAULT, Severity.LOW, NOW)
    await sink.resolve(first.ticket_id, NOW + timedelta(minutes=1))
    second = await sink.open(DEVICE, FAULT, Severity.HIGH, NOW + timedelta(hours=2))

    latest = await sink.latest_for(DEVICE, FAULT)

    assert latest is not None
    assert latest.ticket_id == second.ticket_id


async def test_escalation_updates_severity_in_place(sink: InMemoryTicketSink) -> None:
    ticket = await sink.open(DEVICE, FAULT, Severity.LOW, NOW)

    escalated = await sink.escalate(ticket.ticket_id, Severity.CRITICAL, NOW + timedelta(minutes=2))

    assert escalated.ticket_id == ticket.ticket_id
    assert escalated.severity is Severity.CRITICAL
    assert escalated.status is TicketStatus.OPEN
    assert len(sink.tickets) == 1


async def test_resolving_records_the_closing_time(sink: InMemoryTicketSink) -> None:
    ticket = await sink.open(DEVICE, FAULT, Severity.LOW, NOW)
    closed_at = NOW + timedelta(minutes=10)

    resolved = await sink.resolve(ticket.ticket_id, closed_at)

    assert resolved.status is TicketStatus.CLOSED
    assert resolved.closed_at == closed_at


async def test_operating_on_an_unknown_ticket_is_an_error(sink: InMemoryTicketSink) -> None:
    with pytest.raises(TicketNotFoundError):
        await sink.escalate("AS-9999", Severity.LOW, NOW)


async def test_recent_tickets_are_newest_first_and_bounded(sink: InMemoryTicketSink) -> None:
    for index in range(5):
        await sink.open(
            DeviceId(f"AC-{index + 1:04d}"), FAULT, Severity.LOW, NOW + timedelta(minutes=index)
        )

    recent = await sink.list_recent(limit=3)

    assert len(recent) == 3
    assert [t.device_id.value for t in recent] == ["AC-0005", "AC-0004", "AC-0003"]
