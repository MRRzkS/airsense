"""Replay engine behaviour, exercised without a broker."""

import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import pytest

from simulator.replay import CHANNEL_COLUMNS, ReplayEngine, load_tracks


@dataclass(slots=True)
class RecordingPublisher:
    sent: list[tuple[str, dict[str, object]]] = field(default_factory=list)

    async def publish(self, topic: str, payload: str, qos: int = 0) -> None:
        self.sent.append((topic, json.loads(payload)))


def make_engine(rows: int = 3, devices: int = 2) -> ReplayEngine:
    tracks = {
        f"AC-{device + 1:04d}": [
            {column: float(index + device) for column in CHANNEL_COLUMNS} for index in range(rows)
        ]
        for device in range(devices)
    }
    return ReplayEngine(
        tracks=tracks,
        host="broker",
        port=1883,
        topic_prefix="airsense/telemetry",
        client_id="test",
        interval_seconds=0.0,
    )


async def test_each_tick_publishes_one_frame_per_device() -> None:
    engine, publisher = make_engine(devices=3), RecordingPublisher()

    await engine._tick(publisher)

    assert [topic for topic, _ in publisher.sent] == [
        "airsense/telemetry/AC-0001",
        "airsense/telemetry/AC-0002",
        "airsense/telemetry/AC-0003",
    ]


async def test_payload_carries_every_channel_and_an_offset_aware_timestamp() -> None:
    engine, publisher = make_engine(), RecordingPublisher()

    await engine._tick(publisher)
    _, payload = publisher.sent[0]

    assert set(payload) == {"device_id", "recorded_at", "sequence", *CHANNEL_COLUMNS}
    assert str(payload["recorded_at"]).endswith("+00:00")


async def test_sequence_keeps_climbing_after_the_trajectory_loops() -> None:
    # The fixture is finite but the demo runs indefinitely. Wrapping the frame
    # index must not wrap the sequence, or history would appear to go backwards.
    engine, publisher = make_engine(rows=2, devices=1), RecordingPublisher()

    for _ in range(5):
        await engine._tick(publisher)

    sequences = [payload["sequence"] for _, payload in publisher.sent]
    assert sequences == [0, 1, 2, 3, 4]


async def test_channel_values_cycle_through_the_trajectory() -> None:
    engine, publisher = make_engine(rows=2, devices=1), RecordingPublisher()

    for _ in range(3):
        await engine._tick(publisher)

    currents = [payload["compressor_current_a"] for _, payload in publisher.sent]
    assert currents == [0.0, 1.0, 0.0]


def test_tracks_load_from_parquet_sorted_by_sequence(tmp_path: Path) -> None:
    fixture = tmp_path / "replay.parquet"
    frame = pd.DataFrame(
        {
            "device_id": ["AC-0001", "AC-0001", "AC-0002"],
            "sequence": [1, 0, 0],
            **{column: [1.0, 2.0, 3.0] for column in CHANNEL_COLUMNS},
        }
    )
    frame.to_parquet(fixture, index=False)

    tracks = load_tracks(fixture)

    assert sorted(tracks) == ["AC-0001", "AC-0002"]
    assert len(tracks["AC-0001"]) == 2
    assert tracks["AC-0001"][0]["compressor_current_a"] == pytest.approx(2.0)
