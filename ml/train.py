"""Train the compressor degradation model and export it to ONNX.

    python train.py --raw data/raw/train_FD001.txt

Writes every artifact the running system needs into artifacts/. Seeded
throughout, so the same input reproduces the same model.
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import Pipeline

import export_onnx
from cmapss import REPLAY_STRIDE
from evaluate import regression_metrics, warning_lead_time
from features import (
    FEATURE_NAMES,
    GROUP,
    KNEE_SAMPLES,
    LABEL,
    WINDOW_SIZE,
    build_dataset,
)

SEED: Final = 20260727
TEST_UNIT_FRACTION: Final = 0.2
ARTIFACTS: Final = Path("artifacts")
MODEL_FILE: Final = ARTIFACTS / "compressor_degradation.onnx"

# Conversion is lossy at the float32 boundary. Anything beyond this means the
# exported graph is not the model that was evaluated.
MAX_EXPORT_DRIFT: Final = 1e-4


def build_model() -> Pipeline:
    # Gradient boosting rather than XGBoost: at six thousand rows there is no
    # accuracy to be gained, and sklearn's converter is first-party in skl2onnx
    # where XGBoost needs onnxmltools and its own version pinning.
    #
    # No StandardScaler. Trees split on thresholds and are invariant to monotone
    # rescaling, so it bought nothing — and it added a float32 rounding step
    # ahead of every split comparison, which showed up as a 1e-2 disagreement
    # between sklearn and the exported graph.
    return Pipeline(
        [
            (
                "model",
                GradientBoostingRegressor(
                    n_estimators=200,
                    max_depth=3,
                    learning_rate=0.05,
                    subsample=0.9,
                    random_state=SEED,
                ),
            ),
        ]
    )


def split_by_unit(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Hold out whole units, never individual rows.

    Consecutive rows from one unit share a rolling window and are almost
    identical. Splitting by row would put near-duplicates on both sides and
    report a score the model cannot reproduce on an engine it has never seen.
    """
    splitter = GroupShuffleSplit(n_splits=1, test_size=TEST_UNIT_FRACTION, random_state=SEED)
    train_index, test_index = next(splitter.split(frame, groups=frame[GROUP]))
    return frame.iloc[train_index], frame.iloc[test_index]


def write_artifacts(metrics: dict[str, object], drift: float, rows: int, units: int) -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    (ARTIFACTS / "feature_spec.json").write_text(
        json.dumps(
            {
                "window_size": WINDOW_SIZE,
                "input_name": export_onnx.INPUT_NAME,
                "features": FEATURE_NAMES,
                "label": LABEL,
                "knee_samples": KNEE_SAMPLES,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (ARTIFACTS / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    (ARTIFACTS / "model_card.md").write_text(
        _model_card(metrics, drift, rows, units), encoding="utf-8"
    )


def _model_card(metrics: dict[str, object], drift: float, rows: int, units: int) -> str:
    held_out = metrics["held_out"]
    lead = metrics["warning_lead_time"]
    return f"""# Model card — compressor degradation

Generated {datetime.now(UTC).date().isoformat()} by `ml/train.py`. Do not edit by hand.

## What it predicts

A **health index** in [0, 1]: 0.0 while a unit looks healthy, ramping linearly
to 1.0 at the point of failure. Flat at zero until the unit is within
{KNEE_SAMPLES} samples of failure, because degradation is not observable before
that and a linear target would force the model to fit noise.

It does **not** predict remaining useful life in wall-clock time, a specific
failure mode, or anything about a real air conditioner. See the repository
README's "Limitations and Honest Scope".

## Data

NASA C-MAPSS FD001 turbofan run-to-failure simulation, sensor channels remapped
to split-AC semantics. {rows} windowed samples from {units} units, stride
{REPLAY_STRIDE}. Held-out split is by unit, never by row.

## Architecture

GradientBoostingRegressor (200 trees, depth 3, lr 0.05) over a
{WINDOW_SIZE}-sample rolling window, exported to ONNX opset
{export_onnx.TARGET_OPSET} and scored in-process by onnxruntime.

No feature scaling: trees split on thresholds and are invariant to monotone
rescaling, and removing the scaler cut sklearn/ONNX disagreement from 1e-2 to
1e-7 by dropping a float32 rounding step ahead of every split comparison.

## Held-out performance

| Metric | Value |
| ------ | ----- |
| RMSE | {held_out["rmse"]:.4f} |
| MAE | {held_out["mae"]:.4f} |
| R² | {held_out["r2"]:.4f} |

Warning lead time at threshold {lead["threshold"]}: median
**{lead["median_lead_samples"]:.0f} samples** before failure across
{lead["units_evaluated"]:.0f} held-out units, worst case
{lead["min_lead_samples"]:.0f}, never flagged {lead["units_never_flagged"]:.0f}.

sklearn/ONNX maximum disagreement: {drift:.2e}.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=Path("data/raw/train_FD001.txt"))
    args = parser.parse_args()

    frame = build_dataset(args.raw)
    train_frame, test_frame = split_by_unit(frame)

    model = build_model()
    model.fit(train_frame[FEATURE_NAMES], train_frame[LABEL])

    predictions = model.predict(test_frame[FEATURE_NAMES])
    metrics: dict[str, object] = {
        "held_out": regression_metrics(test_frame[LABEL].to_numpy(), predictions),
        "training": regression_metrics(
            train_frame[LABEL].to_numpy(), model.predict(train_frame[FEATURE_NAMES])
        ),
        "warning_lead_time": warning_lead_time(test_frame[GROUP], predictions),
        "rows": {"train": len(train_frame), "test": len(test_frame)},
        "units": {
            "train": int(train_frame[GROUP].nunique()),
            "test": int(test_frame[GROUP].nunique()),
        },
    }

    export_onnx.export(model, len(FEATURE_NAMES), MODEL_FILE)
    drift = export_onnx.verify(model, test_frame[FEATURE_NAMES].head(256), MODEL_FILE)
    if drift > MAX_EXPORT_DRIFT:
        raise SystemExit(f"ONNX export disagrees with sklearn by {drift:.3e}; refusing to ship")

    write_artifacts(metrics, drift, len(frame), int(frame[GROUP].nunique()))

    print(json.dumps(metrics, indent=2))
    print(f"\nexported {MODEL_FILE} (max drift {drift:.2e})")


if __name__ == "__main__":
    main()
