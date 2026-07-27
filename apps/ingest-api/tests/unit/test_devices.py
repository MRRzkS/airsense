from fastapi.testclient import TestClient

from tests.conftest import Doubles
from tests.fakes import make_scored


def test_fleet_is_empty_before_any_telemetry(client: TestClient) -> None:
    response = client.get("/devices")

    assert response.status_code == 200
    assert response.json() == []


def test_fleet_returns_the_latest_reading_per_device(client: TestClient, doubles: Doubles) -> None:
    doubles.snapshot.by_device = {
        "AC-0002": make_scored("AC-0002", sequence=3),
        "AC-0001": make_scored("AC-0001", sequence=7),
    }

    body = client.get("/devices").json()

    assert [entry["device_id"] for entry in body] == ["AC-0001", "AC-0002"]


def test_fleet_exposes_the_health_index(client: TestClient, doubles: Doubles) -> None:
    doubles.snapshot.by_device = {
        "AC-0001": make_scored("AC-0001", health_index=0.72),
        "AC-0002": make_scored("AC-0002", health_index=None),
    }

    body = client.get("/devices").json()

    assert [entry["health_index"] for entry in body] == [0.72, None]


def test_history_returns_one_device_oldest_first(client: TestClient, doubles: Doubles) -> None:
    doubles.repository.rows = [
        make_scored("AC-0001", sequence=0),
        make_scored("AC-0002", sequence=0),
        make_scored("AC-0001", sequence=1),
    ]

    body = client.get("/devices/AC-0001/readings").json()

    assert [entry["sequence"] for entry in body] == [0, 1]


def test_history_rejects_a_malformed_device_id(client: TestClient) -> None:
    response = client.get("/devices/not-a-device/readings")

    assert response.status_code == 422
    assert "malformed device id" in response.json()["detail"]


def test_history_limit_is_bounded(client: TestClient) -> None:
    assert client.get("/devices/AC-0001/readings", params={"limit": 0}).status_code == 422
    assert client.get("/devices/AC-0001/readings", params={"limit": 9001}).status_code == 422
