"""Turn a degradation score into a device condition and, when warranted, a ticket."""

from dataclasses import dataclass
from datetime import datetime

import structlog

from airsense.application.ports.conditions import ConditionStore
from airsense.application.ports.ticketing import TicketSink
from airsense.domain.conditions import ConditionPolicy, DeviceCondition
from airsense.domain.severity import SeverityPolicy
from airsense.domain.telemetry import DeviceId
from airsense.domain.ticketing import FaultClass, TicketAction, TicketPolicy

log = structlog.get_logger("rules")


@dataclass(frozen=True, slots=True)
class AssessDegradation:
    """Apply the four domain rules to one device, and act on the result.

    Returns the device's condition after this reading. The rules themselves
    live in `domain`; this orchestrates them and talks to the ports.
    """

    conditions: ConditionStore
    sink: TicketSink
    condition_policy: ConditionPolicy
    severity_policy: SeverityPolicy
    ticket_policy: TicketPolicy
    history_samples: int

    async def __call__(
        self, device_id: DeviceId, health_index: float | None, now: datetime
    ) -> DeviceCondition:
        state = await self.conditions.load(device_id)
        if health_index is None:
            return state.condition

        previous = state.condition
        state = state.with_score(health_index, keep=self.history_samples)
        condition = self.condition_policy.evaluate(previous, state.recent_scores)
        await self.conditions.save(device_id, state.at(condition))

        if condition is not previous:
            log.info(
                "device.transition",
                device_id=device_id.value,
                was=previous.value,
                now=condition.value,
                health_index=round(health_index, 4),
            )

        # A device that was normal and stayed normal cannot have a ticket to
        # act on, so skip the CRM round trip entirely. This holds only because
        # condition state is durable; if it were in process memory a restart
        # would strand an open ticket here forever.
        if condition is DeviceCondition.NORMAL and previous is DeviceCondition.NORMAL:
            return condition

        await self._apply(device_id, condition, state.recent_scores, now)
        return condition

    async def _apply(
        self,
        device_id: DeviceId,
        condition: DeviceCondition,
        recent_scores: tuple[float, ...],
        now: datetime,
    ) -> None:
        fault_class = FaultClass.COMPRESSOR_DEGRADATION
        severity = self.severity_policy.evaluate(recent_scores[-1], recent_scores)
        existing = await self.sink.latest_for(device_id, fault_class)
        decision = self.ticket_policy.decide(
            condition=condition, severity=severity, existing=existing, now=now
        )

        if decision.action is TicketAction.OPEN and decision.severity is not None:
            ticket = await self.sink.open(device_id, fault_class, decision.severity, now)
            log.info(
                "ticket.opened",
                device_id=device_id.value,
                ticket_id=ticket.ticket_id,
                severity=ticket.severity.value,
                diagnostic_code=ticket.diagnostic_code,
            )
        elif existing is None:
            return
        elif decision.action is TicketAction.ESCALATE and decision.severity is not None:
            await self.sink.escalate(existing.ticket_id, decision.severity, now)
            log.info(
                "ticket.escalated",
                ticket_id=existing.ticket_id,
                severity=decision.severity.value,
            )
        elif decision.action is TicketAction.RESOLVE:
            await self.sink.resolve(existing.ticket_id, now)
            log.info("ticket.resolved", ticket_id=existing.ticket_id)
        elif decision.action is TicketAction.SUPPRESS:
            log.info("ticket.suppressed", device_id=device_id.value, reason=decision.reason)
