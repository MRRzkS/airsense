"""The feature vector definition — order is the entire contract with the model."""

import json
from pathlib import Path
from statistics import fmean, pstdev

import pytest

from airsense.domain.features import (
    FEATURE_NAMES,
    WINDOW_SIZE,
    InsufficientHistoryError,
    build_feature_vector,
)
from airsense.domain.telemetry import Channel
from tests.fakes import make_reading

# Written by ml/train.py. The offline and online builders live in separate
# installable packages, so this file is the contract that stops them drifting.
FEATURE_SPEC = Path(__file__).parents[4] / "ml" / "artifacts" / "feature_spec.json"


def window(size: int = WINDOW_SIZE, **ramp: float) -> list:
    """A window whose named channels ramp linearly from 0 to the given value."""
    return [
        make_reading(
            sequence=index,
            **{name: value * index / max(size - 1, 1) for name, value in ramp.items()},
        )
        for index in range(size)
    ]


def test_vector_length_matches_the_declared_feature_names() -> None:
    assert len(build_feature_vector(window())) == len(FEATURE_NAMES)


def test_a_short_window_is_refused_rather_than_padded() -> None:
    with pytest.raises(InsufficientHistoryError, match=f"exactly {WINDOW_SIZE}"):
        build_feature_vector(window(WINDOW_SIZE - 1))


def test_an_overlong_window_is_refused_rather_than_truncated() -> None:
    # Silently taking the tail would hide a caller whose deque is misconfigured.
    with pytest.raises(InsufficientHistoryError):
        build_feature_vector(window(WINDOW_SIZE + 1))


def test_statistics_are_computed_over_the_whole_window() -> None:
    readings = window(compressor_current_a=8.0)
    series = [r.compressor_current_a for r in readings]

    vector = build_feature_vector(readings)
    value, mean, std, delta = vector[:4]

    assert value == pytest.approx(series[-1])
    assert mean == pytest.approx(fmean(series))
    assert std == pytest.approx(pstdev(series))
    assert delta == pytest.approx(series[-1] - series[0])


def test_delta_is_signed_so_a_falling_channel_reads_negative() -> None:
    # Discharge pressure falls as a compressor wears. An unsigned magnitude
    # would make wear indistinguishable from recovery.
    readings = [
        make_reading(sequence=i, discharge_pressure_kpa=2800.0 - 20.0 * i)
        for i in range(WINDOW_SIZE)
    ]

    vector = build_feature_vector(readings)
    delta = vector[FEATURE_NAMES.index("discharge_pressure_kpa__delta")]

    assert delta < 0


def test_a_flat_channel_has_zero_spread_and_zero_delta() -> None:
    vector = build_feature_vector(window())

    for name in ("compressor_current_a__std", "compressor_current_a__delta"):
        assert vector[FEATURE_NAMES.index(name)] == pytest.approx(0.0)


def test_names_cover_every_channel_and_are_unique() -> None:
    assert len(set(FEATURE_NAMES)) == len(FEATURE_NAMES)
    for channel in Channel:
        assert sum(name.startswith(f"{channel.value}__") for name in FEATURE_NAMES) == 4


@pytest.mark.skipif(not FEATURE_SPEC.exists(), reason="model artifacts not built")
def test_feature_names_match_the_committed_model_spec() -> None:
    spec = json.loads(FEATURE_SPEC.read_text(encoding="utf-8"))

    assert spec["features"] == FEATURE_NAMES
    assert spec["window_size"] == WINDOW_SIZE
