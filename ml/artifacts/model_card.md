# Model card — compressor degradation

Generated 2026-07-27 by `ml/train.py`. Do not edit by hand.

## What it predicts

A **health index** in [0, 1]: 0.0 while a unit looks healthy, ramping linearly
to 1.0 at the point of failure. Flat at zero until the unit is within
42 samples of failure, because degradation is not observable before
that and a linear target would force the model to fit noise.

It does **not** predict remaining useful life in wall-clock time, a specific
failure mode, or anything about a real air conditioner. See the repository
README's "Limitations and Honest Scope".

## Data

NASA C-MAPSS FD001 turbofan run-to-failure simulation, sensor channels remapped
to split-AC semantics. 5005 windowed samples from 100 units, stride
3. Held-out split is by unit, never by row.

## Architecture

GradientBoostingRegressor (200 trees, depth 3, lr 0.05) over a
20-sample rolling window, exported to ONNX opset
17 and scored in-process by onnxruntime.

No feature scaling: trees split on thresholds and are invariant to monotone
rescaling, and removing the scaler cut sklearn/ONNX disagreement from 1e-2 to
1e-7 by dropping a float32 rounding step ahead of every split comparison.

## Held-out performance

| Metric | Value |
| ------ | ----- |
| RMSE | 0.1533 |
| MAE | 0.1186 |
| R² | 0.7876 |

Warning lead time at threshold 0.5: median
**21 samples** before failure across
20 held-out units, worst case
13, never flagged 0.

sklearn/ONNX maximum disagreement: 1.57e-07.
