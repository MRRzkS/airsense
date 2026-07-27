"""The feature vector the degradation model consumes.

Lives in the domain because *what characterises degradation* is a domain
decision, not an implementation detail of whichever runtime happens to score
it. Offline training builds the same vector from the same definition; the
committed `feature_spec.json` and a test on each side keep the two honest.

Stdlib only — no numpy. Twenty floats over a twenty-sample window is not worth
a dependency, and keeping it stdlib is what lets this sit in `domain`.
"""

from collections.abc import Sequence
from statistics import fmean, pstdev
from typing import Final

from airsense.domain.telemetry import Channel, SensorReading

# Twenty samples. At the simulator's pacing that is roughly sixty compressor
# cycles: long enough to average out sensor noise, short enough that a fault
# appearing now is visible in the aggregate within about twenty seconds rather
# than being diluted by minutes of healthy history.
WINDOW_SIZE: Final = 20

# Population standard deviation, not sample. The window is the entire
# population of interest, and the offline builder must pass ddof=0 to match.
_STATISTICS: Final = ("value", "mean", "std", "delta")

FEATURE_NAMES: Final[list[str]] = [
    f"{channel.value}__{statistic}" for channel in Channel for statistic in _STATISTICS
]


class InsufficientHistoryError(ValueError):
    """Raised when a device has not yet reported a full window."""


def build_feature_vector(window: Sequence[SensorReading]) -> list[float]:
    """Reduce a full window of readings to one feature vector.

    The window must hold exactly `WINDOW_SIZE` readings, oldest first. Values
    are ordered to match `FEATURE_NAMES` exactly; the model's input layer has no
    names, so order is the entire contract.
    """
    if len(window) != WINDOW_SIZE:
        raise InsufficientHistoryError(f"need exactly {WINDOW_SIZE} readings, got {len(window)}")

    features: list[float] = []
    for channel in Channel:
        series = [reading.channels[channel] for reading in window]
        features.extend(
            (
                series[-1],
                fmean(series),
                pstdev(series),
                series[-1] - series[0],
            )
        )
    return features
