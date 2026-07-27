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


def synthetic_cmapss(rows: int = 200) -> pd.DataFrame:
    """A C-MAPSS-shaped frame whose informative sensors drift monotonically."""
    cycle = np.arange(1, rows + 1)
    progress = cycle / rows
    frame = pd.DataFrame({"unit": 1, "cycle": cycle})
    frame["s11"] = 46.0 + 2.0 * progress
    frame["s7"] = 553.0 - 6.0 * progress
    frame["s2"] = 641.0 + 1.5 * progress
    frame["s4"] = 1400.0 + 40.0 * progress
    return frame


@pytest.fixture
def mapped() -> pd.DataFrame:
    frame = synthetic_cmapss()
    return to_ac_channels(
        frame,
        Calibration.fit(frame),
        sample_interval_s=60.0,
        rng=np.random.default_rng(0),
    )


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


def test_ambient_is_independent_of_degradation() -> None:
    frame = synthetic_cmapss()
    degraded = frame.copy()
    for sensor in SOURCE_SENSOR.values():
        degraded[sensor] = degraded[sensor] * 1.5

    kwargs = {"sample_interval_s": 60.0}
    baseline = to_ac_channels(frame, Calibration.fit(frame), rng=np.random.default_rng(7), **kwargs)
    shifted = to_ac_channels(
        degraded, Calibration.fit(degraded), rng=np.random.default_rng(7), **kwargs
    )

    pd.testing.assert_series_equal(
        baseline["ambient_temperature_c"], shifted["ambient_temperature_c"]
    )


def test_ambient_follows_a_diurnal_swing() -> None:
    seconds = np.linspace(0, 86_400, 400)
    ambient = synthesize_ambient(seconds, rng=np.random.default_rng(1))

    assert 20.0 < float(ambient.mean()) < 28.0
    assert float(ambient.max() - ambient.min()) > 8.0


def test_degenerate_calibration_is_rejected() -> None:
    frame = synthetic_cmapss()
    for sensor in SOURCE_SENSOR.values():
        frame[sensor] = 1.0

    with pytest.raises(ValueError, match="degenerate calibration"):
        to_ac_channels(
            frame,
            Calibration.fit(frame),
            sample_interval_s=60.0,
            rng=np.random.default_rng(0),
        )
