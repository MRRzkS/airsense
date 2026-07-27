"""Invariants on a scored reading."""

import pytest

from airsense.domain.scoring import ScoredReading
from tests.fakes import make_reading


@pytest.mark.parametrize("health_index", [0.0, 0.5, 1.0, None])
def test_valid_scores_are_accepted(health_index: float | None) -> None:
    assert ScoredReading(make_reading(), health_index).health_index == health_index


@pytest.mark.parametrize("health_index", [-0.01, 1.01, 42.0])
def test_scores_outside_the_unit_interval_are_rejected(health_index: float) -> None:
    with pytest.raises(ValueError, match="health_index out of range"):
        ScoredReading(make_reading(), health_index)


def test_unscored_is_distinguishable_from_healthy() -> None:
    # The rules engine treats these differently: 0.0 is evidence of health,
    # None is absence of evidence.
    assert ScoredReading(make_reading(), None).is_scored is False
    assert ScoredReading(make_reading(), 0.0).is_scored is True
