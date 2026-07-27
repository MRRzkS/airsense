"""Domain invariants for telemetry value objects."""

from datetime import UTC, datetime

import pytest

from airsense.domain.telemetry import (
    PLAUSIBLE_RANGE,
    Channel,
    DeviceId,
    ImplausibleReadingError,
    SensorReading,
)
from tests.fakes import NOMINAL, make_reading


@pytest.mark.parametrize("value", ["AC-0001", "AC-9999"])
def test_well_formed_device_ids_are_accepted(value: str) -> None:
    assert str(DeviceId(value)) == value


@pytest.mark.parametrize("value", ["", "AC-1", "ac-0001", "AC-00001", "0001", "AC-abcd"])
def test_malformed_device_ids_are_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="malformed device id"):
        DeviceId(value)


def test_naive_timestamps_are_rejected() -> None:
    # A fleet spans installation sites; a timestamp without an offset cannot be
    # ordered against one from another site.
    with pytest.raises(ImplausibleReadingError, match="timezone-aware"):
        SensorReading.from_channels(
            device_id=DeviceId("AC-0001"),
            recorded_at=datetime.now(),  # noqa: DTZ005
            sequence=0,
            channels=dict(NOMINAL),
        )


def test_negative_sequence_is_rejected() -> None:
    with pytest.raises(ImplausibleReadingError, match="negative sequence"):
        make_reading(sequence=-1)


def test_missing_channel_is_named_in_the_error() -> None:
    channels = dict(NOMINAL)
    del channels[Channel.VIBRATION_RMS]

    with pytest.raises(ImplausibleReadingError, match="vibration_rms_mm_s"):
        SensorReading.from_channels(
            device_id=DeviceId("AC-0001"),
            recorded_at=datetime.now(UTC),
            sequence=0,
            channels=channels,
        )


@pytest.mark.parametrize("channel", list(Channel))
def test_values_outside_the_plausible_envelope_are_rejected(channel: Channel) -> None:
    _, high = PLAUSIBLE_RANGE[channel]

    with pytest.raises(ImplausibleReadingError, match=channel.value):
        make_reading(**{channel.value: high + 1.0})


def test_readings_are_immutable() -> None:
    reading = make_reading()

    with pytest.raises((AttributeError, TypeError)):
        reading.compressor_current_a = 9.0  # type: ignore[misc]


def test_channels_exposes_every_declared_sensor() -> None:
    assert set(make_reading().channels) == set(Channel)
