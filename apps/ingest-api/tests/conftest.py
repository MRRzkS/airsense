import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

# Connection settings have no defaults by design, so the suite supplies them
# before anything constructs Settings.
_TEST_ENV = {
    "ENVIRONMENT": "ci",
    "DATABASE_DSN": "postgresql+asyncpg://airsense:airsense@localhost:5432/airsense_test",
    "REDIS_DSN": "redis://localhost:6379/1",
    "MQTT_HOST": "localhost",
}


@pytest.fixture(scope="session", autouse=True)
def test_environment() -> Iterator[None]:
    for key, value in _TEST_ENV.items():
        os.environ.setdefault(key, value)
    yield


@pytest.fixture
def client(test_environment: None) -> Iterator[TestClient]:
    # Imported lazily so the environment above is in place before Settings is
    # instantiated at import time.
    from airsense.api.app import create_app

    with TestClient(create_app()) as test_client:
        yield test_client
