"""The four rules working together on a stream of scores."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from airsense.application.use_cases.assess_degradation import AssessDegradation
from airsense.domain.conditions import DeviceCondition
from airsense.domain.severity import Severity
from airsense.domain.telemetry import DeviceId
from airsense.domain.ticketing import TicketPolicy, TicketStatus
from airsense.infrastructure.crm.memory import InMemoryTicketSink
from tests.fakes import (
    DEMO_CONDITION_POLICY,
    DEMO_SEVERITY_POLICY,
    InMemoryConditionStore,
)

START = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)
DEVICE = DeviceId("AC-0001")


@dataclass(slots=True)
class Rig:
    assess: AssessDegradation
    sink: InMemoryTicketSink
    conditions: InMemoryConditionStore
    clock: datetime = START

    async def feed(self, scores: list[float | None], step: timedelta = timedelta(seconds=1)):
        condition = DeviceCondition.NORMAL
        for score in scores:
            condition = await self.assess(DEVICE, score, self.clock)
            self.clock += step
        return condition

    def advance(self, delta: timedelta) -> None:
        self.clock += delta


def build_rig(cooldown: timedelta = timedelta(minutes=30)) -> Rig:
    sink = InMemoryTicketSink()
    conditions = InMemoryConditionStore()
    return Rig(
        assess=AssessDegradation(
            conditions=conditions,
            sink=sink,
            condition_policy=DEMO_CONDITION_POLICY,
            severity_policy=DEMO_SEVERITY_POLICY,
            ticket_policy=TicketPolicy(cooldown=cooldown),
            history_samples=20,
        ),
        sink=sink,
        conditions=conditions,
    )


# ─── Warm-up ──────────────────────────────────────────────────────────────


async def test_unscored_readings_are_not_assessed() -> None:
    # A device filling its first feature window has no score. Treating that as
    # 0.0 would record it as healthy on no evidence.
    rig = build_rig()

    condition = await rig.feed([None] * 10)

    assert condition is DeviceCondition.NORMAL
    assert rig.sink.tickets == {}
    assert rig.conditions.states == {}


# ─── The acceptance path ──────────────────────────────────────────────────


async def test_a_sustained_alert_opens_exactly_one_ticket() -> None:
    rig = build_rig()

    condition = await rig.feed([0.85] * 30)

    assert condition is DeviceCondition.ALERT
    assert len(rig.sink.tickets) == 1


async def test_the_ticket_carries_device_fault_class_and_severity() -> None:
    rig = build_rig()

    await rig.feed([0.85] * 10)
    ticket = next(iter(rig.sink.tickets.values()))

    assert ticket.device_id == DEVICE
    assert ticket.diagnostic_code == "F1-07"
    assert ticket.severity in set(Severity)
    assert ticket.status is TicketStatus.OPEN


async def test_a_device_climbs_normal_then_watch_then_alert() -> None:
    rig = build_rig()
    seen: list[DeviceCondition] = []

    for score in [0.1] * 3 + [0.55] * 3 + [0.85] * 3:
        seen.append(await rig.assess(DEVICE, score, rig.clock))
        rig.clock += timedelta(seconds=1)

    assert seen[2] is DeviceCondition.NORMAL
    assert seen[5] is DeviceCondition.WATCH
    assert seen[8] is DeviceCondition.ALERT


# ─── Rule 1 end to end ────────────────────────────────────────────────────


async def test_a_spike_in_healthy_telemetry_files_nothing() -> None:
    rig = build_rig()

    await rig.feed([0.05, 0.05, 0.99, 0.05, 0.05, 0.05])

    assert rig.sink.tickets == {}


# ─── Rule 2 end to end ────────────────────────────────────────────────────


async def test_deterioration_escalates_rather_than_duplicating() -> None:
    rig = build_rig()

    await rig.feed([0.78] * 6)
    opened = next(iter(rig.sink.tickets.values()))
    await rig.feed([0.99] * 6)

    assert len(rig.sink.tickets) == 1
    escalated = rig.sink.tickets[opened.ticket_id]
    assert escalated.severity.rank > opened.severity.rank


# ─── Rules 3 and 4 end to end ─────────────────────────────────────────────


async def test_recovery_resolves_the_ticket_then_cooldown_blocks_a_reopen() -> None:
    rig = build_rig(cooldown=timedelta(minutes=30))

    await rig.feed([0.85] * 6)
    ticket_id = next(iter(rig.sink.tickets))

    await rig.feed([0.0] * 9)
    assert rig.sink.tickets[ticket_id].status is TicketStatus.CLOSED

    await rig.feed([0.85] * 9)
    assert len(rig.sink.tickets) == 1, "cooldown should have suppressed the reopen"


async def test_a_reopen_is_allowed_once_the_cooldown_expires() -> None:
    rig = build_rig(cooldown=timedelta(minutes=30))

    await rig.feed([0.85] * 6)
    await rig.feed([0.0] * 9)
    rig.advance(timedelta(hours=1))
    await rig.feed([0.85] * 9)

    assert len(rig.sink.tickets) == 2


# ─── State durability ─────────────────────────────────────────────────────


async def test_condition_state_is_persisted_between_readings() -> None:
    # Held in the store rather than in the use case, so a restart resumes mid
    # debounce instead of resetting an alerting device to NORMAL.
    rig = build_rig()

    await rig.feed([0.85] * 5)

    stored = rig.conditions.states[DEVICE.value]
    assert stored.condition is DeviceCondition.ALERT
    assert stored.recent_scores == pytest.approx((0.85,) * 5)
