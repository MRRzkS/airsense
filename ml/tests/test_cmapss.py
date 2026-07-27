import numpy as np
import pandas as pd
import pytest

from cmapss import (
    SOURCE_SENSOR,
    TARGET_RANGE,
    Calibration,
    synthesize_ambient,
    to_ac_channels,
)

# Close to a real FD001 trajectory after the builder's stride-3 downsample.
TRAJECTORY_SAMPLES = 110


def synthetic_cmapss(rows: int = TRAJECTORY_SAMPLES, units: int = 1) -> pd.DataFrame:
    """A C-MAPSS-shaped frame whose informative sensors drift monotonically."""
    frames = []
    for unit in range(1, units + 1):
        cycle = np.arange(1, rows + 1)
        progress = cycle / rows
        frame = pd.DataFrame({"unit": unit, "cycle": cycle})
        frame["s11"] = 46.0 + 2.0 * progress
        frame["s7"] = 553.0 - 6.0 * progress
        frame["s2"] = 641.0 + 1.5 * progress
        frame["s4"] = 1400.0 + 40.0 * progress
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def map_frame(frame: pd.DataFrame, seed: int = 0) -> pd.DataFrame:
    return to_ac_channels(frame, Calibration.fit(frame), rng=np.random.default_rng(seed))


@pytest.fixture
def mapped() -> pd.DataFrame:
    return map_frame(synthetic_cmapss())


@pytest.mark.parametrize("channel", list(TARGET_RANGE))
def test_channels_land_inside_their_target_envelope(mapped: pd.DataFrame, channel: str) -> None:
    low, high = TARGET_RANGE[channel]
    assert mapped[channel].min() >= low - 1e-9
    assert mapped[channel].max() <= high + 1e-9


def test_rising_source_sensors_produce_rising_channels(mapped: pd.DataFrame) -> None:
    # s11, s2 and s4 climb with wear, so current, suction temperature and
    # vibration must climb too.
    for channel in ("compressor_current_a", "suction_temperature_c", "vibration_rms_mm_s"):
        assert mapped[channel].iloc[-1] > mapped[channel].iloc[0]


def test_falling_discharge_pressure_survives_the_mapping(mapped: pd.DataFrame) -> None:
    # A worn compressor loses discharge pressure; s7 falls, so the AC channel
    # must fall as well rather than being silently normalised into rising.
    assert mapped["discharge_pressure_kpa"].iloc[-1] < mapped["discharge_pressure_kpa"].iloc[0]


def test_ambient_does_not_track_wear_over_a_full_trajectory() -> None:
    # Regression: with the diurnal period set in wall-clock seconds, a
    # trajectory covered only the rising quarter of the sine, so ambient
    # climbed monotonically and leaked degradation into a channel that is
    # supposed to be independent of it.
    frame = synthetic_cmapss()
    mapped = map_frame(frame)
    progress = frame["cycle"] / frame["cycle"].max()

    correlation = float(mapped["ambient_temperature_c"].corr(progress))

    assert abs(correlation) < 0.25, f"ambient leaks wear (corr={correlation:.3f})"


def test_ambient_is_unchanged_by_degradation_severity() -> None:
    frame = synthetic_cmapss()
    degraded = frame.copy()
    for sensor in SOURCE_SENSOR.values():
        degraded[sensor] = degraded[sensor] * 1.5

    baseline = map_frame(frame, seed=7)
    shifted = map_frame(degraded, seed=7)

    pd.testing.assert_series_equal(
        baseline["ambient_temperature_c"], shifted["ambient_temperature_c"]
    )


def test_units_do_not_swing_in_lockstep() -> None:
    # A per-unit phase offset; otherwise the whole fleet warms and cools
    # together, which no real installed base does.
    mapped = map_frame(synthetic_cmapss(units=2))
    first, second = (
        mapped[mapped["unit"] == unit]["ambient_temperature_c"].to_numpy() for unit in (1, 2)
    )

    assert not np.allclose(first, second, atol=0.5)


def test_ambient_covers_a_realistic_daily_span() -> None:
    ambient = synthesize_ambient(
        np.arange(TRAJECTORY_SAMPLES), phase=0.0, rng=np.random.default_rng(1)
    )

    assert 20.0 < float(ambient.mean()) < 28.0
    assert float(ambient.max() - ambient.min()) > 8.0


def test_degenerate_calibration_is_rejected() -> None:
    frame = synthetic_cmapss()
    for sensor in SOURCE_SENSOR.values():
        frame[sensor] = 1.0

    with pytest.raises(ValueError, match="degenerate calibration"):
        map_frame(frame)
