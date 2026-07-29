"""Replay engine behaviour, exercised without a broker."""

import json
from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path

import pandas as pd
import pytest

from simulator.replay import (
    CHANNEL_COLUMNS,
    ReplayEngine,
    Trajectory,
    load_trajectories,
)


@dataclass(slots=True)
class RecordingPublisher:
    sent: list[tuple[str, dict[str, object]]] = field(default_factory=list)

    async def publish(self, topic: str, payload: str, qos: int = 0) -> None:
        self.sent.append((topic, json.loads(payload)))

    def values(self, key: str = "compressor_current_a") -> list[float]:
        return [float(payload[key]) for _, payload in self.sent]  # type: ignore[arg-type]


def make_engine(
    frames: int = 10, healthy: int = 4, devices: int = 1, ramp: int | None = None
) -> ReplayEngine:
    # Channel values equal their frame index, so a published series reads
    # directly as the path taken through the trajectory.
    trajectories = {
        f"AC-{device + 1:04d}": Trajectory(
            frames=[dict.fromkeys(CHANNEL_COLUMNS, float(index)) for index in range(frames)],
            healthy_frames=healthy,
            ramp_start=healthy if ramp is None else ramp,
        )
        for device in range(devices)
    }
    return ReplayEngine(
        trajectories=trajectories,
        host="broker",
        port=1883,
        topic_prefix="airsense/telemetry",
        client_id="test",
        interval_seconds=0.0,
    )


async def drive(engine: ReplayEngine, ticks: int) -> RecordingPublisher:
    publisher = RecordingPublisher()
    for _ in range(ticks):
        await engine._tick(publisher)
    return publisher


# ─── Publishing shape ─────────────────────────────────────────────────────


async def test_each_tick_publishes_one_frame_per_device() -> None:
    publisher = await drive(make_engine(devices=3), ticks=1)

    assert [topic for topic, _ in publisher.sent] == [
        "airsense/telemetry/AC-0001",
        "airsense/telemetry/AC-0002",
        "airsense/telemetry/AC-0003",
    ]


async def test_payload_carries_every_channel_and_an_offset_aware_timestamp() -> None:
    publisher = await drive(make_engine(), ticks=1)
    _, payload = publisher.sent[0]

    assert set(payload) == {"device_id", "recorded_at", "sequence", *CHANNEL_COLUMNS}
    assert str(payload["recorded_at"]).endswith("+00:00")


async def test_sequence_keeps_climbing_regardless_of_position() -> None:
    # The trajectory is finite but the demo runs indefinitely. Reusing frames
    # must not rewind the sequence, or history would appear to go backwards.
    publisher = await drive(make_engine(frames=4, healthy=2), ticks=6)

    assert [payload["sequence"] for _, payload in publisher.sent] == [0, 1, 2, 3, 4, 5]


# ─── Healthy idling ───────────────────────────────────────────────────────


async def test_an_idle_device_stays_inside_its_healthy_prefix() -> None:
    # An untouched fleet must never self-alert: the reviewer clicks the button.
    publisher = await drive(make_engine(frames=10, healthy=4), ticks=20)

    assert max(publisher.values()) <= 3.0


async def test_idling_ping_pongs_rather_than_jumping_back_to_the_start() -> None:
    # Wrapping to frame zero would step the channels discontinuously, and the
    # model's delta feature is computed across exactly that step.
    publisher = await drive(make_engine(frames=10, healthy=4), ticks=8)

    assert publisher.values() == [0.0, 1.0, 2.0, 3.0, 2.0, 1.0, 0.0, 1.0]


async def test_consecutive_idle_frames_never_jump_by_more_than_one() -> None:
    publisher = await drive(make_engine(frames=12, healthy=5), ticks=40)
    values = publisher.values()

    assert all(abs(b - a) == 1.0 for a, b in pairwise(values))


# ─── Fault injection ──────────────────────────────────────────────────────


async def test_injection_starts_at_the_ramp_not_at_failure() -> None:
    # Teleporting to the end would hand the scorer a feature vector unlike
    # anything in its training set.
    engine = make_engine(frames=10, healthy=4)
    engine.inject_fault("AC-0001")

    publisher = await drive(engine, ticks=1)

    assert publisher.values() == [4.0]


async def test_an_injected_device_runs_forward_to_failure_and_holds() -> None:
    engine = make_engine(frames=10, healthy=4)
    engine.inject_fault("AC-0001")

    publisher = await drive(engine, ticks=10)

    assert publisher.values() == [4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 9.0, 9.0, 9.0, 9.0]


async def test_injecting_one_device_leaves_the_rest_healthy() -> None:
    engine = make_engine(frames=10, healthy=4, devices=2)
    engine.inject_fault("AC-0002")

    publisher = await drive(engine, ticks=6)
    untouched = [
        v
        for (topic, _), v in zip(publisher.sent, publisher.values(), strict=True)
        if topic.endswith("AC-0001")
    ]

    assert max(untouched) <= 3.0


async def test_injecting_an_unknown_device_is_rejected() -> None:
    with pytest.raises(KeyError):
        make_engine().inject_fault("AC-9999")


async def test_reset_returns_a_device_to_idling() -> None:
    engine = make_engine(frames=10, healthy=4)
    engine.inject_fault("AC-0001")
    await drive(engine, ticks=4)

    engine.reset_all()
    publisher = await drive(engine, ticks=3)

    assert engine.is_faulted("AC-0001") is False
    assert publisher.values() == [0.0, 1.0, 2.0]


# ─── Loading ──────────────────────────────────────────────────────────────


async def test_injection_enters_the_ramp_not_the_healthy_boundary() -> None:
    # Entering at the healthy boundary is faithful but slow: the model needs
    # most of the ramp before the score clears the alert threshold.
    engine = make_engine(frames=10, healthy=4, ramp=6)
    engine.inject_fault("AC-0001")

    publisher = await drive(engine, ticks=3)

    assert publisher.values() == [6.0, 7.0, 8.0]


def build_fixture(path: Path) -> None:
    pd.DataFrame(
        {
            "device_id": ["AC-0001"] * 6,
            "sequence": [5, 0, 1, 2, 3, 4],
            "life_fraction": [1.0, 0.2, 0.4, 0.55, 0.7, 0.9],
            **{column: [6.0, 1.0, 2.0, 3.0, 4.0, 5.0] for column in CHANNEL_COLUMNS},
        }
    ).to_parquet(path, index=False)


def test_trajectories_load_with_an_idle_span_and_an_injection_point(tmp_path: Path) -> None:
    fixture = tmp_path / "replay.parquet"
    build_fixture(fixture)

    trajectories = load_trajectories(fixture, healthy_ceiling=0.45, injection_start=0.60)

    trajectory = trajectories["AC-0001"]
    assert trajectory.healthy_frames == 2
    assert trajectory.ramp_start == 3
    assert trajectory.frames[0]["compressor_current_a"] == pytest.approx(1.0)


def test_an_injection_point_inside_the_idle_span_is_rejected(tmp_path: Path) -> None:
    fixture = tmp_path / "replay.parquet"
    build_fixture(fixture)

    with pytest.raises(ValueError, match="healthy_ceiling < injection_start"):
        load_trajectories(fixture, healthy_ceiling=0.7, injection_start=0.6)


def test_a_trajectory_must_be_internally_consistent() -> None:
    with pytest.raises(ValueError, match="at least one frame"):
        Trajectory(frames=[], healthy_frames=1, ramp_start=1)

    with pytest.raises(ValueError, match="ramp_start must sit at or after"):
        Trajectory(frames=[{}, {}, {}], healthy_frames=2, ramp_start=1)
