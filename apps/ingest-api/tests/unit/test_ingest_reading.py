"""The ingest use case's ordering and scoring contract."""

from dataclasses import dataclass

import pytest

from airsense.application.use_cases.ingest_reading import IngestReading
from tests.fakes import (
    ExplodingReadingRepository,
    InMemoryReadingRepository,
    InMemorySnapshot,
    InMemoryStream,
    StubScorer,
    make_reading,
)


@dataclass(slots=True)
class Rig:
    ingest: IngestReading
    repository: InMemoryReadingRepository
    snapshot: InMemorySnapshot
    stream: InMemoryStream
    scorer: StubScorer


def build_rig(score: float | None = 0.25) -> Rig:
    repository = InMemoryReadingRepository()
    snapshot = InMemorySnapshot()
    stream = InMemoryStream()
    scorer = StubScorer(value=score)
    return Rig(
        ingest=IngestReading(
            repository=repository, snapshot=snapshot, stream=stream, scorer=scorer
        ),
        repository=repository,
        snapshot=snapshot,
        stream=stream,
        scorer=scorer,
    )


async def test_reading_reaches_history_cache_and_stream() -> None:
    rig = build_rig()
    reading = make_reading()

    await rig.ingest(reading)

    assert [row.reading for row in rig.repository.rows] == [reading]
    assert rig.snapshot.by_device["AC-0001"].reading == reading
    assert [row.reading for row in rig.stream.published] == [reading]


async def test_the_model_score_is_attached_before_anything_is_written() -> None:
    rig = build_rig(score=0.61)

    await rig.ingest(make_reading())

    # All three sinks must agree; a score that differed between history and the
    # live stream would make the chart disagree with itself on reload.
    assert rig.repository.rows[0].health_index == pytest.approx(0.61)
    assert rig.snapshot.by_device["AC-0001"].health_index == pytest.approx(0.61)
    assert rig.stream.published[0].health_index == pytest.approx(0.61)


async def test_a_warming_up_device_is_stored_unscored_rather_than_as_zero() -> None:
    rig = build_rig(score=None)

    await rig.ingest(make_reading())

    assert rig.repository.rows[0].health_index is None
    assert rig.repository.rows[0].is_scored is False


async def test_a_failed_write_does_not_fan_out() -> None:
    # History is the only durable record. Publishing a reading the database
    # rejected would show operators a value that no longer exists anywhere.
    snapshot, stream = InMemorySnapshot(), InMemoryStream()
    ingest = IngestReading(
        repository=ExplodingReadingRepository(),
        snapshot=snapshot,
        stream=stream,
        scorer=StubScorer(),
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        await ingest(make_reading())

    assert snapshot.by_device == {}
    assert stream.published == []


async def test_latest_reading_replaces_the_previous_snapshot() -> None:
    rig = build_rig()

    await rig.ingest(make_reading(sequence=0, compressor_current_a=4.4))
    await rig.ingest(make_reading(sequence=1, compressor_current_a=6.9))

    assert rig.snapshot.by_device["AC-0001"].reading.compressor_current_a == pytest.approx(6.9)


async def test_every_reading_is_offered_to_the_scorer_in_order() -> None:
    # The scorer keeps a rolling window, so skipping or reordering submissions
    # silently corrupts its features.
    rig = build_rig()

    for sequence in range(4):
        await rig.ingest(make_reading(sequence=sequence))

    assert [reading.sequence for reading in rig.scorer.seen] == [0, 1, 2, 3]
