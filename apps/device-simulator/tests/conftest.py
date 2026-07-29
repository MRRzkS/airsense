import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

_TEST_ENV = {"ENVIRONMENT": "ci", "MQTT_HOST": "localhost"}


@pytest.fixture(scope="session", autouse=True)
def test_environment() -> Iterator[None]:
    for key, value in _TEST_ENV.items():
        os.environ.setdefault(key, value)
    yield


@pytest.fixture
def client(test_environment: None) -> Iterator[TestClient]:
    from simulator.api import create_app

    # Constructed without the context manager on purpose: entering it would run
    # lifespan, which loads the real fixture and starts a replay task that
    # retries against a broker that is not there. Tests attach their own engine.
    yield TestClient(create_app())
