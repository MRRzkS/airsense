"""Rules 2 and 4 — ticket deduplication and cooldown."""

from datetime import UTC, datetime, timedelta

import pytest

from airsense.domain.conditions import DeviceCondition
from airsense.domain.severity import Severity
from airsense.domain.telemetry import DeviceId
from airsense.domain.ticketing import (
    FaultClass,
    Ticket,
    TicketAction,
    TicketPolicy,
    TicketStatus,
)

NOW = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)
COOLDOWN = timedelta(minutes=30)
POLICY = TicketPolicy(cooldown=COOLDOWN)
DEVICE = DeviceId("AC-0001")
FAULT = FaultClass.COMPRESSOR_DEGRADATION


def open_ticket(severity: Severity = Severity.MEDIUM) -> Ticket:
    return Ticket(
        ticket_id="AS-0001",
        device_id=DEVICE,
        fault_class=FAULT,
        severity=severity,
        status=TicketStatus.OPEN,
        opened_at=NOW - timedelta(minutes=5),
        updated_at=NOW - timedelta(minutes=5),
    )


def closed_ticket(closed_ago: timedelta) -> Ticket:
    closed_at = NOW - closed_ago
    return Ticket(
        ticket_id="AS-0001",
        device_id=DEVICE,
        fault_class=FAULT,
        severity=Severity.HIGH,
        status=TicketStatus.CLOSED,
        opened_at=closed_at - timedelta(hours=1),
        updated_at=closed_at,
        closed_at=closed_at,
    )


def decide(
    condition: DeviceCondition,
    severity: Severity = Severity.MEDIUM,
    existing: Ticket | None = None,
    now: datetime = NOW,
):
    return POLICY.decide(condition=condition, severity=severity, existing=existing, now=now)


# ─── Ticket invariants ────────────────────────────────────────────────────


def test_a_closed_ticket_must_record_when_it_closed() -> None:
    with pytest.raises(ValueError, match="must record when it closed"):
        Ticket(
            ticket_id="AS-1",
            device_id=DEVICE,
            fault_class=FAULT,
            severity=Severity.LOW,
            status=TicketStatus.CLOSED,
            opened_at=NOW,
            updated_at=NOW,
        )


def test_an_open_ticket_cannot_have_a_closing_time() -> None:
    with pytest.raises(ValueError, match="cannot have a closing time"):
        Ticket(
            ticket_id="AS-1",
            device_id=DEVICE,
            fault_class=FAULT,
            severity=Severity.LOW,
            status=TicketStatus.OPEN,
            opened_at=NOW,
            updated_at=NOW,
            closed_at=NOW,
        )


def test_a_ticket_carries_a_diagnostic_code() -> None:
    assert open_ticket().diagnostic_code == "F1-07"


def test_a_naive_now_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        decide(DeviceCondition.ALERT, now=datetime(2026, 7, 27, 12, 0))  # noqa: DTZ001


# ─── Opening ──────────────────────────────────────────────────────────────


def test_a_sustained_alert_opens_a_ticket() -> None:
    decision = decide(DeviceCondition.ALERT, Severity.HIGH)

    assert decision.action is TicketAction.OPEN
    assert decision.severity is Severity.HIGH


@pytest.mark.parametrize("condition", [DeviceCondition.NORMAL, DeviceCondition.WATCH])
def test_watch_and_normal_do_not_open_tickets(condition: DeviceCondition) -> None:
    # WATCH is observation. Opening a ticket for every device that wobbles is
    # exactly the noise the CRM must not receive.
    assert decide(condition).action is TicketAction.HOLD


# ─── Rule 2: deduplication ────────────────────────────────────────────────


def test_re_alerting_does_not_open_a_second_ticket() -> None:
    decision = decide(DeviceCondition.ALERT, Severity.MEDIUM, existing=open_ticket())

    assert decision.action is TicketAction.HOLD
    assert "already open" in decision.reason


def test_deterioration_escalates_the_existing_ticket() -> None:
    decision = decide(DeviceCondition.ALERT, Severity.CRITICAL, existing=open_ticket(Severity.LOW))

    assert decision.action is TicketAction.ESCALATE
    assert decision.severity is Severity.CRITICAL


def test_severity_ratchets_and_never_falls_while_open() -> None:
    # A technician dispatched against a HIGH ticket must not find it quietly
    # downgraded because the unit had a good minute.
    decision = decide(DeviceCondition.ALERT, Severity.LOW, existing=open_ticket(Severity.HIGH))

    assert decision.action is TicketAction.HOLD
    assert decision.severity is Severity.HIGH


# ─── Rule 4: cooldown ─────────────────────────────────────────────────────


def test_a_recently_closed_ticket_blocks_a_reopen() -> None:
    decision = decide(
        DeviceCondition.ALERT, existing=closed_ticket(closed_ago=timedelta(minutes=5))
    )

    assert decision.action is TicketAction.SUPPRESS
    assert "cooldown" in decision.reason


def test_the_boundary_is_exclusive() -> None:
    assert decide(DeviceCondition.ALERT, existing=closed_ticket(COOLDOWN)).action is (
        TicketAction.OPEN
    )
    assert (
        decide(
            DeviceCondition.ALERT, existing=closed_ticket(COOLDOWN - timedelta(seconds=1))
        ).action
        is TicketAction.SUPPRESS
    )


def test_a_ticket_may_reopen_once_the_quiet_period_has_passed() -> None:
    decision = decide(DeviceCondition.ALERT, existing=closed_ticket(timedelta(hours=2)))

    assert decision.action is TicketAction.OPEN


def test_a_zero_cooldown_permits_immediate_reopen() -> None:
    permissive = TicketPolicy(cooldown=timedelta(0))

    decision = permissive.decide(
        condition=DeviceCondition.ALERT,
        severity=Severity.HIGH,
        existing=closed_ticket(timedelta(0)),
        now=NOW,
    )

    assert decision.action is TicketAction.OPEN


def test_a_negative_cooldown_is_rejected() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        TicketPolicy(cooldown=timedelta(minutes=-1))


# ─── Resolution ───────────────────────────────────────────────────────────


def test_returning_to_normal_resolves_an_open_ticket() -> None:
    decision = decide(DeviceCondition.NORMAL, existing=open_ticket())

    assert decision.action is TicketAction.RESOLVE


def test_dropping_only_to_watch_keeps_the_ticket_open() -> None:
    # Closing on the way down would re-open on the next oscillation, which is
    # what the cooldown exists to catch. Better not to close at all.
    decision = decide(DeviceCondition.WATCH, existing=open_ticket())

    assert decision.action is TicketAction.HOLD


def test_normal_with_an_already_closed_ticket_does_nothing() -> None:
    decision = decide(DeviceCondition.NORMAL, existing=closed_ticket(timedelta(days=1)))

    assert decision.action is TicketAction.HOLD
