# Offline model training

Populated in **P2**. This directory produces exactly one artifact the running
system consumes: an ONNX file scored in-process by `ingest-api`.

## Data

Training uses **NASA C-MAPSS turbofan degradation simulation (FD001)**. The raw
files are *not* committed — see `.gitignore`. Download them into `data/raw/`
before running training.

The sensor channels are remapped to split-AC semantics (compressor current,
discharge pressure, suction temperature, ambient temperature, vibration RMS).
This is a **domain mapping, not real appliance telemetry**, and the top-level
README says so in its "Limitations and Honest Scope" section.

## Layout (P2)

```
features.py     feature engineering shared with the online scorer
train.py        seeded, reproducible training
evaluate.py     held-out metrics written to artifacts/metrics.json
export_onnx.py  skl2onnx export
artifacts/      committed: .onnx, model_card.md, metrics.json
```
