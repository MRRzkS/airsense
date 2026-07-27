"""Offline feature and label construction.

Mirrors `airsense.domain.features` — same window, same statistics, same
ordering. The two live in separate installable packages, so `feature_spec.json`
is written here at training time and asserted against the domain definition by a
test on the ingest side. If they ever drift, that test fails rather than the
model silently scoring garbage.
"""

from pathlib import Path
from typing import Final

import numpy as np
import pandas as pd

from cmapss import (
    CHANNEL_COLUMNS,
    REPLAY_STRIDE,
    Calibration,
    load_raw,
    to_ac_channels,
)

# Must equal airsense.domain.features.WINDOW_SIZE.
WINDOW_SIZE: Final = 20

STATISTICS: Final = ("value", "mean", "std", "delta")

FEATURE_NAMES: Final[list[str]] = [
    f"{channel}__{statistic}" for channel in CHANNEL_COLUMNS for statistic in STATISTICS
]

# Degradation is not observable early in a unit's life; the sensors simply look
# healthy. Regressing on a linear time-to-failure target therefore forces the
# model to fit noise across the flat majority of every trajectory. The standard
# C-MAPSS treatment is a piecewise-linear health index: flat at zero until the
# unit is within a knee of failure, then ramping to one. 42 samples is 125
# original cycles at stride 3, the conventional C-MAPSS knee.
KNEE_SAMPLES: Final = 42

LABEL = "health_index"
GROUP = "unit"


def build_dataset(raw_path: Path) -> pd.DataFrame:
    """Produce a model-ready frame of features, label and unit id.

    Rows without a full window are dropped: a partial window would produce
    features on a different scale from every other row.
    """
    raw = load_raw(raw_path)
    calibration = Calibration.fit(raw)

    downsampled = raw[raw["cycle"] % REPLAY_STRIDE == 1].copy()
    mapped = to_ac_channels(downsampled, calibration, rng=np.random.default_rng(20260727))

    frame = pd.DataFrame({GROUP: mapped[GROUP]}, index=mapped.index)
    for channel in CHANNEL_COLUMNS:
        grouped = mapped.groupby(GROUP)[channel]
        frame[f"{channel}__value"] = mapped[channel]
        frame[f"{channel}__mean"] = grouped.transform(lambda s: s.rolling(WINDOW_SIZE).mean())
        # ddof=0 to match statistics.pstdev on the online side.
        frame[f"{channel}__std"] = grouped.transform(lambda s: s.rolling(WINDOW_SIZE).std(ddof=0))
        frame[f"{channel}__delta"] = mapped[channel] - grouped.transform(
            lambda s: s.shift(WINDOW_SIZE - 1)
        )

    frame[LABEL] = _health_index(mapped)
    return frame.dropna().reset_index(drop=True)


def _health_index(mapped: pd.DataFrame) -> pd.Series:
    """0.0 while a unit looks healthy, ramping to 1.0 at the point of failure."""
    position = mapped.groupby(GROUP).cumcount()
    last_position = mapped.groupby(GROUP)[GROUP].transform("size") - 1
    remaining = last_position - position
    return (1.0 - remaining / KNEE_SAMPLES).clip(lower=0.0, upper=1.0)
