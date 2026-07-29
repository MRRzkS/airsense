"""The fault injection control surface."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from simulator.api import limiter
from simulator.config import get_settings
from simulator.replay import CHANNEL_COLUMNS, ReplayEngine, Trajectory


@pytest.fixture(autouse=True)
def clean_limiter() -> Iterator[None]:
    # slowapi's default storage is module-level and would otherwise carry
    # request counts from one test into the next.
    limiter.reset()
    yield
    limiter.reset()


def attach_engine(client: TestClient, devices: int = 2) -> ReplayEngine:
    engine = ReplayEngine(
        trajectories={
            f"AC-{index + 1:04d}": Trajectory(
                frames=[dict.fromkeys(CHANNEL_COLUMNS, float(i)) for i in range(10)],
                healthy_frames=4,
                ramp_start=6,
            )
            for index in range(devices)
        },
        host="broker",
        port=1883,
        topic_prefix="airsense/telemetry",
        client_id="test",
        interval_seconds=0.0,
    )
    client.app.state.engine = engine  # type: ignore[union-attr]
    return engine


def test_fleet_reports_which_devices_are_faulted(client: TestClient) -> None:
    engine = attach_engine(client)
    engine.inject_fault("AC-0002")

    body = client.get("/devices").json()

    assert body["devices"] == [
        {"device_id": "AC-0001", "faulted": False},
        {"device_id": "AC-0002", "faulted": True},
    ]


def test_injecting_marks_the_device_faulted(client: TestClient) -> None:
    engine = attach_engine(client)

    response = client.post("/faults/inject", json={"device_id": "AC-0001"})

    assert response.status_code == 200
    assert response.json()["faulted"] is True
    assert engine.is_faulted("AC-0001")


def test_injecting_an_unknown_device_is_a_404(client: TestClient) -> None:
    attach_engine(client)

    response = client.post("/faults/inject", json={"device_id": "AC-9999"})

    assert response.status_code == 404


def test_injecting_without_a_fixture_is_a_503(client: TestClient) -> None:
    # The engine is None when no replay fixture was found on disk.
    response = client.post("/faults/inject", json={"device_id": "AC-0001"})

    assert response.status_code == 503
    assert "fixture" in response.json()["detail"]


def test_reset_clears_every_fault(client: TestClient) -> None:
    engine = attach_engine(client)
    engine.inject_fault("AC-0001")
    engine.inject_fault("AC-0002")

    body = client.post("/faults/reset").json()

    assert all(device["faulted"] is False for device in body["devices"])


def test_the_control_surface_is_rate_limited(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Public in the demo deployment; without a limit one script can drive the
    # broker and the database as hard as it likes.
    monkeypatch.setenv("INJECT_RATE_LIMIT", "3/minute")
    get_settings.cache_clear()
    attach_engine(client)

    statuses = [
        client.post("/faults/inject", json={"device_id": "AC-0001"}).status_code for _ in range(5)
    ]
    get_settings.cache_clear()

    assert statuses[:3] == [200, 200, 200]
    assert statuses[3:] == [429, 429]
