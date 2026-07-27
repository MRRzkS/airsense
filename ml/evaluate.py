"""Held-out evaluation.

Reports regression error, but also warning lead time — the metric a maintenance
business actually buys. An RMSE of 0.08 says nothing about whether a technician
gets dispatched before the customer calls.
"""

from typing import Final

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

# The health index at which P3's rules begin paying attention. Lead time is
# reported at this value so the two stay in step.
WATCH_THRESHOLD: Final = 0.5


def regression_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    return {
        "rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "r2": float(r2_score(y_true, y_pred)),
    }


def warning_lead_time(
    units: pd.Series,
    y_pred: np.ndarray,
    *,
    threshold: float = WATCH_THRESHOLD,
) -> dict[str, float]:
    """How many samples of warning each held-out unit would have received.

    Measured as the gap between the first crossing of `threshold` and the unit's
    final sample. A unit that never crosses counts as zero warning rather than
    being dropped, so silent failures cannot flatter the average.
    """
    frame = pd.DataFrame({"unit": units.to_numpy(), "score": y_pred})
    leads: list[int] = []
    missed = 0

    for _, group in frame.groupby("unit"):
        crossings = np.flatnonzero(group["score"].to_numpy() >= threshold)
        if crossings.size == 0:
            missed += 1
            leads.append(0)
            continue
        leads.append(int(len(group) - 1 - crossings[0]))

    return {
        "threshold": threshold,
        "median_lead_samples": float(np.median(leads)),
        "mean_lead_samples": float(np.mean(leads)),
        "min_lead_samples": float(np.min(leads)),
        "units_never_flagged": float(missed),
        "units_evaluated": float(len(leads)),
    }
