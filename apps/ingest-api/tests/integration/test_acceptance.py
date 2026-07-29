"""The acceptance criterion, exercised in-process.

No containers. The real committed replay fixture, the real exported ONNX model,
and the real domain rules at their *shipped* threshold values, wired straight to
an in-memory ticket sink. What this does not cover is the wire between them —
MQTT, TimescaleDB, Redis and SSE are all stubbed out by construction.

The claim under test: a reviewer clicks Inject Fault and, within the demo's ten
second budget, sees the state walk NORMAL → WATCH → ALERT and a ticket appear.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

# Reading the fixture needs pandas and a working parquet backend. Guarded
# explicitly rather than with importorskip, which re-raises ImportErrors that
# are not a plain "module not found" — a blocked binary is one of those.
try:
    import pandas as pd
    import pyarrow.parquet  # noqa: F401
except ImportError as exc:  # pragma: no cover
    pytest.skip(f"parquet support unavailable: {exc}", allow_module_level=True)

from airsense.application.use_cases.assess_degradation import AssessDegradation
from airsense.domain.conditions import ConditionPolicy, DeviceCondition
from airsense.domain.severity import SeverityPolicy
from airsense.domain.telemetry import Channel, DeviceId, SensorReading
from airsense.domain.ticketing import TicketPolicy
from airsense.infrastructure.config import Settings, get_settings
from airsense.infrastructure.crm.memory import InMemoryTicketSink
from airsense.infrastructure.onnx.scorer import create_scorer
from tests.fakes import InMemoryConditionStore

REPO = Path(__file__).parents[4]
FIXTURE = REPO / "apps" / "device-simulator" / "data" / "replay_fd001.parquet"
MODEL = REPO / "ml" / "artifacts" / "compressor_degradation.onnx"
SPEC = REPO / "ml" / "artifacts" / "feature_spec.json"

pytestmark = pytest.mark.skipif(
    not (FIXTURE.exists() and MODEL.exists()), reason="fixture or model artifacts not built"
)

DEVICE = DeviceId("AC-0001")
CHANNEL_COLUMNS = [channel.value for channel in Channel]

# Simulator defaults, mirrored here so a change to either side shows up as a
# failing budget rather than a slow demo nobody measured.
PUBLISH_HZ = 5.0
HEALTHY_CEILING = 0.45
INJECTION_START = 0.60
DEMO_BUDGET_SAMPLES = int(10 * PUBLISH_HZ)


def split_trajectory(
    device_id: str = DEVICE.value,
) -> tuple[list[dict[str, float]], list[dict[str, float]]]:
    frame = pd.read_parquet(FIXTURE)
    device = frame[frame["device_id"] == device_id].sort_values("sequence")
    healthy = device[device["life_fraction"] <= HEALTHY_CEILING]
    ramp = device[device["life_fraction"] > INJECTION_START]
    return (
        healthy[CHANNEL_COLUMNS].to_dict(orient="records"),
        ramp[CHANNEL_COLUMNS].to_dict(orient="records"),
    )


def production_assessment(sink: InMemoryTicketSink) -> AssessDegradation:
    """Wire the rules exactly as `build_runtime` does, at shipped thresholds."""
    settings: Settings = get_settings()
    return AssessDegradation(
        conditions=InMemoryConditionStore(),
        sink=sink,
        condition_policy=ConditionPolicy(
            watch_enter=settings.watch_enter,
            watch_exit=settings.watch_exit,
            alert_enter=settings.alert_enter,
            alert_exit=settings.alert_exit,
            sustained_samples=settings.sustained_samples,
        ),
        severity_policy=SeverityPolicy(
            medium_band=settings.severity_medium_band,
            high_band=settings.severity_high_band,
            critical_band=settings.severity_critical_band,
            fast_degradation_per_sample=settings.fast_degradation_per_sample,
        ),
        ticket_policy=TicketPolicy(cooldown=timedelta(minutes=settings.ticket_cooldown_minutes)),
        history_samples=settings.condition_history_samples,
    )


class Harness:
    def __init__(self, device_id: str = DEVICE.value) -> None:
        self.device = DeviceId(device_id)
        self.sink = InMemoryTicketSink()
        self.assess = production_assessment(self.sink)
        self.scorer = create_scorer(MODEL, SPEC)
        self.clock = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)
        self.sequence = 0
        self.conditions: list[DeviceCondition] = []
        self.scores: list[float | None] = []

    async def feed(self, rows: list[dict[str, float]]) -> None:
        for row in rows:
            reading = SensorReading.from_channels(
                device_id=self.device,
                recorded_at=self.clock,
                sequence=self.sequence,
                channels={Channel(name): float(value) for name, value in row.items()},
            )
            score = self.scorer.score(reading)
            self.conditions.append(await self.assess(self.device, score, self.clock))
            self.scores.append(score)
            self.sequence += 1
            self.clock += timedelta(seconds=1 / PUBLISH_HZ)

    def first_alert_after(self, offset: int) -> int | None:
        for index, condition in enumerate(self.conditions[offset:]):
            if condition is DeviceCondition.ALERT:
                return index
        return None


def idle_pattern(healthy: list[dict[str, float]], samples: int) -> list[dict[str, float]]:
    """Ping-pong the healthy prefix, matching the simulator's idle behaviour."""
    cycle = healthy + healthy[-2:0:-1]
    return [cycle[index % len(cycle)] for index in range(samples)]


@pytest.fixture
async def idled() -> Harness:
    healthy, _ = split_trajectory()
    harness = Harness()
    await harness.feed(idle_pattern(healthy, samples=60))
    return harness


async def test_an_untouched_fleet_stays_quiet(idled: Harness) -> None:
    # If idling alerts on its own, the demo is broken before anyone clicks.
    assert idled.sink.tickets == {}
    assert set(idled.conditions) == {DeviceCondition.NORMAL}


async def test_idle_scores_stay_below_the_watch_threshold(idled: Harness) -> None:
    scored = [score for score in idled.scores if score is not None]

    assert scored, "the scorer never produced a value"
    assert max(scored) < get_settings().watch_enter


@pytest.mark.parametrize("device_id", ["AC-0001", "AC-0002", "AC-0003", "AC-0004"])
async def test_injecting_a_fault_alerts_inside_the_demo_budget(device_id: str) -> None:
    # Every device the demo ships, not just the first one a reviewer clicks.
    healthy, ramp = split_trajectory(device_id)
    harness = Harness(device_id)
    await harness.feed(idle_pattern(healthy, samples=60))
    before = len(harness.conditions)

    await harness.feed(ramp)

    assert harness.sink.tickets, f"{device_id}: no ticket was ever opened"
    alerted_at = harness.first_alert_after(before)
    assert alerted_at is not None, f"{device_id}: never reached ALERT"
    assert alerted_at <= DEMO_BUDGET_SAMPLES, (
        f"{device_id}: reached ALERT after {alerted_at} samples "
        f"({alerted_at / PUBLISH_HZ:.1f}s); budget is {DEMO_BUDGET_SAMPLES} "
        f"({DEMO_BUDGET_SAMPLES / PUBLISH_HZ:.0f}s)"
    )


async def test_the_state_walks_normal_then_watch_then_alert(idled: Harness) -> None:
    _, ramp = split_trajectory()
    before = len(idled.conditions)

    await idled.feed(ramp)
    walk = idled.conditions[before:]

    assert DeviceCondition.WATCH in walk
    assert walk.index(DeviceCondition.WATCH) < walk.index(DeviceCondition.ALERT)


async def test_exactly_one_ticket_is_filed_for_the_whole_fault(idled: Harness) -> None:
    _, ramp = split_trajectory()

    await idled.feed(ramp)
    # Hold at failure, as the simulator does once the ramp is exhausted.
    await idled.feed([ramp[-1]] * 60)

    assert len(idled.sink.tickets) == 1


async def test_the_filed_ticket_names_the_device_code_and_severity(idled: Harness) -> None:
    _, ramp = split_trajectory()

    await idled.feed(ramp)
    ticket = next(iter(idled.sink.tickets.values()))

    assert ticket.device_id == DEVICE
    assert ticket.diagnostic_code == "F1-07"
    assert ticket.severity.rank >= 1
