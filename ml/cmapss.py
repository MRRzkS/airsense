"""NASA C-MAPSS FD001 loading and the turbofan-to-split-AC channel mapping.

This module is the *only* place raw C-MAPSS is interpreted. The simulator never
sees it: it replays the committed artifact this produces.

Read the honest version of what follows in the README's "Limitations and Honest
Scope" section. In short: C-MAPSS is run-to-failure data from a simulated
turbofan engine. Mapping it onto AC compressor semantics gives realistic
*degradation dynamics* — monotone drift, unit-to-unit variation, sensor noise —
with physically plausible units. It is not appliance telemetry, and no claim is
made that a model trained here transfers to a real air conditioner.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
import pandas as pd

COLUMNS: Final[list[str]] = ["unit", "cycle", "op_1", "op_2", "op_3"] + [
    f"s{i}" for i in range(1, 22)
]

# Which C-MAPSS sensor backs each AC channel, and why the analogy holds.
#
#   s11  Ps30, static pressure at HPC outlet. Rises monotonically with wear ->
#        a compressor drawing more current as it works against fouling.
#   s7   P30, total pressure at HPC outlet. Falls with wear -> a compressor
#        losing discharge pressure as valves and rings wear.
#   s2   T24, LPC outlet temperature. Rises slightly -> suction line warming as
#        cooling capacity is lost.
#   s4   T50, LPT outlet temperature. The cleanest monotone channel in FD001.
#        Used as a mechanical-degradation proxy for vibration; this is the
#        loosest analogy of the five and is called out as such in the README.
SOURCE_SENSOR: Final[dict[str, str]] = {
    "compressor_current_a": "s11",
    "discharge_pressure_kpa": "s7",
    "suction_temperature_c": "s2",
    "vibration_rms_mm_s": "s4",
}

# Nominal operating envelope for a ~3.5 kW residential split unit in cooling
# mode. Deliberately narrower than the domain's PLAUSIBLE_RANGE, which only
# rejects nonsense. Endpoint order encodes direction: the low end of each source
# sensor's observed range maps to the first value.
TARGET_RANGE: Final[dict[str, tuple[float, float]]] = {
    "compressor_current_a": (4.2, 7.8),
    "discharge_pressure_kpa": (1950.0, 2850.0),
    "suction_temperature_c": (6.0, 13.0),
    "vibration_rms_mm_s": (0.8, 6.5),
}

CHANNEL_COLUMNS: Final[list[str]] = [
    "compressor_current_a",
    "discharge_pressure_kpa",
    "suction_temperature_c",
    "ambient_temperature_c",
    "vibration_rms_mm_s",
]

# Keep every third cycle. This shortens the replay enough to loop inside a
# review, but it also has to be applied when building the training set: a
# twenty-sample rolling window covers sixty cycles online, so training on
# full-resolution data would give the same feature a different meaning.
REPLAY_STRIDE: Final = 3

AMBIENT_MEAN_C: Final = 24.0
AMBIENT_SWING_C: Final = 6.0
AMBIENT_NOISE_C: Final = 0.4

# Period in samples, not seconds. A unit's whole trajectory stands in for months
# of service compressed into a couple of minutes of replay, so the day/night
# cycle has to be expressed in replay time. Getting this wrong is not cosmetic:
# at 24h against a ~6h trajectory the sine only traverses its rising quarter,
# which makes ambient climb monotonically and hands the model a spurious
# correlation with wear. Roughly 2.5 full swings per trajectory keeps it honest.
AMBIENT_PERIOD_SAMPLES: Final = 45.0


@dataclass(frozen=True, slots=True)
class Calibration:
    """Robust per-sensor bounds used to rescale into AC units.

    1st/99th percentiles rather than min/max: C-MAPSS carries occasional
    outliers that would otherwise compress the useful range into a few percent
    of the output span.
    """

    low: dict[str, float]
    high: dict[str, float]

    @classmethod
    def fit(cls, frame: pd.DataFrame) -> "Calibration":
        sensors = set(SOURCE_SENSOR.values())
        return cls(
            low={s: float(frame[s].quantile(0.01)) for s in sensors},
            high={s: float(frame[s].quantile(0.99)) for s in sensors},
        )


def load_raw(path: Path) -> pd.DataFrame:
    """Read one whitespace-delimited C-MAPSS file into a typed frame."""
    frame = pd.read_csv(path, sep=r"\s+", header=None, engine="python")
    # The files carry two trailing empty columns from the line-ending format.
    frame = frame.iloc[:, : len(COLUMNS)]
    frame.columns = pd.Index(COLUMNS)
    return frame


def _rescale(
    values: pd.Series, *, low: float, high: float, target: tuple[float, float]
) -> pd.Series:
    if high <= low:
        raise ValueError(f"degenerate calibration bounds: low={low} high={high}")
    lo_out, hi_out = target
    normalized = (values - low) / (high - low)
    return (lo_out + normalized * (hi_out - lo_out)).clip(min(target), max(target))


def synthesize_ambient(
    sample_index: np.ndarray, *, phase: float, rng: np.random.Generator
) -> np.ndarray:
    """Generate outdoor temperature for one unit's trajectory.

    Synthesized rather than mapped: ambient temperature is genuinely
    independent of compressor health, and borrowing a degrading turbofan
    channel for it would fabricate a correlation the model could then exploit.
    `phase` decorrelates units from each other so the fleet does not warm and
    cool in lockstep.
    """
    angle = 2 * np.pi * (sample_index / AMBIENT_PERIOD_SAMPLES + phase)
    swing = AMBIENT_MEAN_C + AMBIENT_SWING_C * np.sin(angle)
    return swing + rng.normal(0.0, AMBIENT_NOISE_C, size=sample_index.shape)


def to_ac_channels(
    frame: pd.DataFrame,
    calibration: Calibration,
    *,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Rescale C-MAPSS sensors into split-AC channels, preserving direction."""
    mapped = pd.DataFrame({"unit": frame["unit"], "cycle": frame["cycle"]}, index=frame.index)
    for channel, sensor in SOURCE_SENSOR.items():
        mapped[channel] = _rescale(
            frame[sensor],
            low=calibration.low[sensor],
            high=calibration.high[sensor],
            target=TARGET_RANGE[channel],
        )

    position = frame.groupby("unit").cumcount()
    ambient = pd.Series(0.0, index=frame.index, dtype=float)
    for unit in frame["unit"].unique():
        rows = frame["unit"] == unit
        ambient.loc[rows] = synthesize_ambient(
            position[rows].to_numpy(), phase=float(rng.random()), rng=rng
        )
    mapped["ambient_temperature_c"] = ambient
    return mapped
