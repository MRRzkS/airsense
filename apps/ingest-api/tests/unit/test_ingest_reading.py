"""The ingest use case's ordering contract."""

import pytest

from airsense.application.use_cases.ingest_reading import IngestReading
from tests.fakes import (
    ExplodingReadingRepository,
    InMemoryReadingRepository,
    InMemorySnapshot,
    InMemoryStream,
    make_reading,
)


async def test_reading_reaches_history_cache_and_stream() -> None:
    repository, snapshot, stream = (
        InMemoryReadingRepository(),
        InMemorySnapshot(),
        InMemoryStream(),
    )
    ingest = IngestReading(repository=repository, snapshot=snapshot, stream=stream)
    reading = make_reading()

    await ingest(reading)

    assert repository.rows == [reading]
    assert snapshot.by_device == {"AC-0001": reading}
    assert stream.published == [reading]


async def test_a_failed_write_does_not_fan_out() -> None:
    # History is the only durable record. Publishing a reading the database
    # rejected would show operators a value that no longer exists anywhere.
    snapshot, stream = InMemorySnapshot(), InMemoryStream()
    ingest = IngestReading(
        repository=ExplodingReadingRepository(),
        snapshot=snapshot,
        stream=stream,
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        await ingest(make_reading())

    assert snapshot.by_device == {}
    assert stream.published == []


async def test_latest_reading_replaces_the_previous_snapshot() -> None:
    snapshot = InMemorySnapshot()
    ingest = IngestReading(
        repository=InMemoryReadingRepository(),
        snapshot=snapshot,
        stream=InMemoryStream(),
    )

    await ingest(make_reading(sequence=0, compressor_current_a=4.4))
    await ingest(make_reading(sequence=1, compressor_current_a=6.9))

    assert snapshot.by_device["AC-0001"].compressor_current_a == pytest.approx(6.9)
