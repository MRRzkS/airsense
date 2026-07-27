import os
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from tests.fakes import (
    InMemoryReadingRepository,
    InMemorySnapshot,
    InMemoryStream,
    StubDependencyHealth,
    StubScorer,
)

# Connection settings have no defaults by design, so the suite supplies them
# before anything constructs Settings.
_TEST_ENV = {
    "ENVIRONMENT": "ci",
    "DATABASE_DSN": "postgresql+asyncpg://airsense:airsense@localhost:5432/airsense_test",
    "REDIS_DSN": "redis://localhost:6379/1",
    "MQTT_HOST": "localhost",
}


@dataclass(slots=True)
class Doubles:
    repository: InMemoryReadingRepository
    snapshot: InMemorySnapshot
    stream: InMemoryStream
    probe: StubDependencyHealth
    scorer: StubScorer


@pytest.fixture(scope="session", autouse=True)
def test_environment() -> Iterator[None]:
    for key, value in _TEST_ENV.items():
        os.environ.setdefault(key, value)
    yield


@pytest.fixture
def doubles() -> Doubles:
    return Doubles(
        repository=InMemoryReadingRepository(),
        snapshot=InMemorySnapshot(),
        stream=InMemoryStream(),
        probe=StubDependencyHealth(),
        scorer=StubScorer(),
    )


@pytest.fixture
def client(test_environment: None, doubles: Doubles) -> Iterator[TestClient]:
    # Imported lazily so the environment above is in place before Settings is
    # instantiated at import time.
    from airsense.api.app import create_app
    from airsense.api.services import Services
    from airsense.application.use_cases.ingest_reading import IngestReading
    from airsense.application.use_cases.query_fleet import ListFleet, ReadHistory

    app = create_app()
    app.state.services = Services(
        stream=doubles.stream,
        probe=doubles.probe,
        ingest=IngestReading(
            repository=doubles.repository,
            snapshot=doubles.snapshot,
            stream=doubles.stream,
            scorer=doubles.scorer,
        ),
        list_fleet=ListFleet(snapshot=doubles.snapshot),
        read_history=ReadHistory(repository=doubles.repository),
    )

    # Constructed without the context manager on purpose: entering it would run
    # lifespan, which opens real database, cache and broker connections.
    yield TestClient(app)
