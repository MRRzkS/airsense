"""The wire format is the contract between the simulator and ingest."""

import pytest
from pydantic import ValidationError

from airsense.domain.telemetry import ImplausibleReadingError
from airsense.infrastructure.wire import TelemetryMessage
from tests.fakes import make_reading

VALID_PAYLOAD = """
{"device_id": "AC-0001", "recorded_at": "2026-07-27T09:00:00Z", "sequence": 12,
 "compressor_current_a": 4.6, "discharge_pressure_kpa": 2780.0,
 "suction_temperature_c": 7.1, "ambient_temperature_c": 26.4,
 "vibration_rms_mm_s": 1.1}
"""


def test_domain_survives_a_round_trip() -> None:
    original = make_reading(sequence=5)

    restored = TelemetryMessage.from_domain(original).to_domain()

    assert restored == original


def test_published_json_parses_into_the_domain() -> None:
    reading = TelemetryMessage.model_validate_json(VALID_PAYLOAD).to_domain()

    assert reading.device_id.value == "AC-0001"
    assert reading.sequence == 12
    assert reading.recorded_at.tzinfo is not None


def test_unknown_fields_are_rejected() -> None:
    # extra="forbid": a producer that starts sending a field we silently drop
    # is a schema drift bug, and it should fail loudly at the boundary.
    payload = VALID_PAYLOAD.replace('"sequence": 12', '"sequence": 12, "rogue_field": 1')

    with pytest.raises(ValidationError):
        TelemetryMessage.model_validate_json(payload)


def test_physically_impossible_values_are_rejected_on_conversion() -> None:
    payload = VALID_PAYLOAD.replace('"compressor_current_a": 4.6', '"compressor_current_a": 400.0')

    with pytest.raises(ImplausibleReadingError, match="compressor_current_a"):
        TelemetryMessage.model_validate_json(payload).to_domain()


def test_naive_timestamps_are_rejected_on_conversion() -> None:
    payload = VALID_PAYLOAD.replace("2026-07-27T09:00:00Z", "2026-07-27T09:00:00")

    with pytest.raises(ImplausibleReadingError, match="timezone-aware"):
        TelemetryMessage.model_validate_json(payload).to_domain()
