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

AMBIENT_MEAN_C: Final = 24.0
AMBIENT_SWING_C: Final = 6.0
AMBIENT_NOISE_C: Final = 0.4
AMBIENT_PERIOD_S: Final = 86_400.0


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


def synthesize_ambient(seconds: np.ndarray, *, rng: np.random.Generator) -> np.ndarray:
    """Generate outdoor temperature.

    Synthesized rather than mapped: ambient temperature is genuinely
    independent of compressor health, and borrowing a degrading turbofan
    channel for it would fabricate a correlation the model could then exploit.
    """
    diurnal = AMBIENT_MEAN_C + AMBIENT_SWING_C * np.sin(2 * np.pi * seconds / AMBIENT_PERIOD_S)
    return diurnal + rng.normal(0.0, AMBIENT_NOISE_C, size=seconds.shape)


def to_ac_channels(
    frame: pd.DataFrame,
    calibration: Calibration,
    *,
    sample_interval_s: float,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Rescale C-MAPSS sensors into split-AC channels, preserving direction."""
    mapped = pd.DataFrame({"unit": frame["unit"], "cycle": frame["cycle"]})
    for channel, sensor in SOURCE_SENSOR.items():
        mapped[channel] = _rescale(
            frame[sensor],
            low=calibration.low[sensor],
            high=calibration.high[sensor],
            target=TARGET_RANGE[channel],
        )

    elapsed = (frame["cycle"].to_numpy() - 1) * sample_interval_s
    mapped["ambient_temperature_c"] = synthesize_ambient(elapsed, rng=rng)
    return mapped
