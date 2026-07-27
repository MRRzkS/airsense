# Offline model training

Produces the single artifact the running system consumes: an ONNX file scored
in-process by `ingest-api`.

## Data

**NASA C-MAPSS FD001** turbofan run-to-failure simulation, from the NASA
Prognostics Center of Excellence. The raw files are *not* committed. Download
`CMAPSSData.zip` from the PCoE data set repository and place `train_FD001.txt`
in `data/raw/`.

Sensor channels are remapped to split-AC semantics in `cmapss.py`. This is a
**domain mapping, not real appliance telemetry** — see the top-level README's
"Limitations and Honest Scope".

## What the model predicts

A **health index** in [0, 1]: 0.0 while a unit looks healthy, ramping to 1.0 at
the modelled point of failure. Flat at zero until the unit is within a knee of
failure, because degradation is not observable before that and a linear target
would force the model to fit noise across the flat majority of every trajectory.

It does not predict remaining useful life in wall-clock time, and it does not
identify a failure mode.

## Running it

```bash
pip install -e ".[train,dev]"
python build_replay_fixture.py   # writes the simulator's committed parquet
python train.py                  # writes everything in artifacts/
```

Both are seeded, so the same input reproduces the same output.

## Files

```
cmapss.py                 raw loading + the turbofan-to-AC channel mapping
features.py               offline feature and label construction
train.py                  training entry point
evaluate.py               held-out metrics, including warning lead time
export_onnx.py            skl2onnx conversion and round-trip verification
build_replay_fixture.py   builds the simulator's replay parquet
artifacts/                committed: .onnx, feature_spec.json, metrics.json, model_card.md
```

## Two things worth knowing

**The split is by unit, never by row.** Consecutive rows from one engine share a
rolling window and are nearly identical; splitting by row would put
near-duplicates on both sides and report a score the model cannot reproduce on
an engine it has not seen.

**The export is verified, not assumed.** `train.py` scores the same rows through
both scikit-learn and the exported ONNX graph and refuses to write the artifact
if they disagree by more than 1e-4. This caught a real 1e-2 discrepancy caused
by a `StandardScaler` rounding features to float32 ahead of every tree split —
the scaler was useless for a tree model anyway and was removed.
