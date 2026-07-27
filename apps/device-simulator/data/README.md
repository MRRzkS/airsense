# Replay data

This directory holds the **derived** replay fixture the simulator publishes to
MQTT. It is committed so that `make up` produces a working demo with no download
step.

- `replay_fd001.parquet` — 452 rows, 4 devices, ~105–121 frames each. A
  stride-3 downsample of the four longest-lived units in NASA C-MAPSS FD001,
  with sensor channels remapped to split-AC semantics (compressor current,
  discharge pressure, suction temperature, ambient temperature, vibration RMS).
  Regenerate with `python ml/build_replay_fixture.py`; the seed is fixed, so the
  same input reproduces the same file.
- `raw/` — gitignored. The original C-MAPSS text files, if you want to
  regenerate the fixture or retrain. See `ml/README.md` for where to get them.

The mapping from turbofan sensors to AC channels is a **domain mapping, not real
appliance data**. The README's "Limitations and Honest Scope" section says so in
full; do not present this as field telemetry.
