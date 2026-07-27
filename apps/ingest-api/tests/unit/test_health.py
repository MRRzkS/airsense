from fastapi.testclient import TestClient

from tests.conftest import Doubles


def test_health_reports_service_identity(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "ingest-api"
    assert body["environment"] == "ci"


def test_ready_is_200_when_every_dependency_answers(client: TestClient) -> None:
    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"database": "ok", "cache": "ok"}}


def test_ready_is_503_and_names_the_broken_dependency(client: TestClient, doubles: Doubles) -> None:
    doubles.probe.result = {"database": "ok", "cache": "ConnectionError"}

    response = client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["cache"] == "ConnectionError"


def test_metrics_endpoint_serves_prometheus_exposition(client: TestClient) -> None:
    response = client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "airsense_readings_ingested_total" in response.text
