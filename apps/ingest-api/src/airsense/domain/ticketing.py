"""Rules 2 and 4 — ticket deduplication and cooldown.

Firing a ticket every time a threshold is crossed produces hundreds of tickets
for one broken compressor. Two rules prevent that:

* **Deduplication.** At most one open ticket per (device, fault class). A device
  that keeps alerting updates the existing ticket's severity; it never opens a
  second.
* **Cooldown.** Once a ticket closes, the same fault class cannot re-open for a
  quiet period. Without it a unit sitting on the threshold closes and re-opens a
  ticket on every oscillation, and the CRM fills with churn that looks like many
  faults instead of one unresolved one.

Severity ratchets while a ticket is open: it can rise, never fall. A technician
dispatched against a HIGH ticket should not find it silently downgraded because
the unit had a good hour.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Final

from airsense.domain.conditions import DeviceCondition
from airsense.domain.severity import Severity, worst
from airsense.domain.telemetry import DeviceId


class FaultClass(StrEnum):
    COMPRESSOR_DEGRADATION = "COMPRESSOR_DEGRADATION"


# Service codes in the shape field engineers actually quote down the phone.
# Illustrative — this is not any manufacturer's real code table.
FAULT_CODE: Final[dict[FaultClass, str]] = {
    FaultClass.COMPRESSOR_DEGRADATION: "F1-07",
}


class TicketStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class TicketAction(StrEnum):
    OPEN = "OPEN"
    ESCALATE = "ESCALATE"
    RESOLVE = "RESOLVE"
    SUPPRESS = "SUPPRESS"
    HOLD = "HOLD"


@dataclass(frozen=True, slots=True)
class Ticket:
    ticket_id: str
    device_id: DeviceId
    fault_class: FaultClass
    severity: Severity
    status: TicketStatus
    opened_at: datetime
    updated_at: datetime
    closed_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.opened_at.tzinfo is None or self.updated_at.tzinfo is None:
            raise ValueError("ticket timestamps must be timezone-aware")
        if self.status is TicketStatus.CLOSED and self.closed_at is None:
            raise ValueError("a closed ticket must record when it closed")
        if self.status is TicketStatus.OPEN and self.closed_at is not None:
            raise ValueError("an open ticket cannot have a closing time")

    @property
    def is_open(self) -> bool:
        return self.status is TicketStatus.OPEN

    @property
    def diagnostic_code(self) -> str:
        return FAULT_CODE[self.fault_class]


@dataclass(frozen=True, slots=True)
class TicketDecision:
    action: TicketAction
    severity: Severity | None = None
    reason: str = ""


@dataclass(frozen=True, slots=True)
class TicketPolicy:
    """Decides what should happen to a device's ticket, given its condition."""

    cooldown: timedelta

    def __post_init__(self) -> None:
        if self.cooldown < timedelta(0):
            raise ValueError("cooldown cannot be negative")

    def decide(
        self,
        *,
        condition: DeviceCondition,
        severity: Severity,
        existing: Ticket | None,
        now: datetime,
    ) -> TicketDecision:
        """Return the single action to take for one (device, fault class)."""
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware")

        if condition is not DeviceCondition.ALERT:
            return self._while_not_alerting(condition, existing)

        if existing is not None and existing.is_open:
            target = worst(existing.severity, severity)
            if target.rank > existing.severity.rank:
                return TicketDecision(TicketAction.ESCALATE, target, "condition deteriorated")
            # Deduplication: the fault is already represented in the CRM.
            return TicketDecision(TicketAction.HOLD, existing.severity, "ticket already open")

        if existing is not None and existing.closed_at is not None:
            quiet_for = now - existing.closed_at
            if quiet_for < self.cooldown:
                return TicketDecision(
                    TicketAction.SUPPRESS,
                    severity,
                    f"within {self.cooldown} cooldown of ticket {existing.ticket_id}",
                )

        return TicketDecision(TicketAction.OPEN, severity, "sustained alert condition")

    def _while_not_alerting(
        self, condition: DeviceCondition, existing: Ticket | None
    ) -> TicketDecision:
        if existing is None or not existing.is_open:
            return TicketDecision(TicketAction.HOLD, reason="nothing open")
        # WATCH keeps the ticket open: the unit is still degraded, and closing
        # on the way down would re-open it on the next oscillation.
        if condition is DeviceCondition.WATCH:
            return TicketDecision(TicketAction.HOLD, existing.severity, "still degraded")
        return TicketDecision(
            TicketAction.RESOLVE, existing.severity, "condition returned to normal"
        )
