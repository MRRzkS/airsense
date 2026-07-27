"""The CRM panel's endpoint."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from airsense.domain.severity import Severity
from airsense.domain.telemetry import DeviceId
from airsense.domain.ticketing import FaultClass
from tests.conftest import Doubles

NOW = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)


def test_panel_is_empty_before_anything_is_filed(client: TestClient) -> None:
    response = client.get("/tickets")

    assert response.status_code == 200
    assert response.json() == []


async def test_a_ticket_is_serialized_with_everything_the_panel_shows(
    client: TestClient, doubles: Doubles
) -> None:
    await doubles.sink.open(
        DeviceId("AC-0007"), FaultClass.COMPRESSOR_DEGRADATION, Severity.HIGH, NOW
    )

    body = client.get("/tickets").json()

    assert len(body) == 1
    ticket = body[0]
    assert ticket["device_id"] == "AC-0007"
    assert ticket["severity"] == "HIGH"
    assert ticket["status"] == "OPEN"
    assert ticket["diagnostic_code"] == "F1-07"
    assert ticket["closed_at"] is None


async def test_tickets_are_newest_first(client: TestClient, doubles: Doubles) -> None:
    for index in range(3):
        await doubles.sink.open(
            DeviceId(f"AC-{index + 1:04d}"),
            FaultClass.COMPRESSOR_DEGRADATION,
            Severity.LOW,
            NOW + timedelta(minutes=index),
        )

    body = client.get("/tickets").json()

    assert [t["device_id"] for t in body] == ["AC-0003", "AC-0002", "AC-0001"]


def test_limit_is_bounded(client: TestClient) -> None:
    assert client.get("/tickets", params={"limit": 0}).status_code == 422
    assert client.get("/tickets", params={"limit": 500}).status_code == 422
