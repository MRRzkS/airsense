"""Build the committed replay fixture from raw C-MAPSS FD001.

Run once; the parquet it writes is committed so `make up` needs no download.

    python build_replay_fixture.py --raw data/raw/train_FD001.txt
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from cmapss import (
    CHANNEL_COLUMNS,
    REPLAY_STRIDE,
    Calibration,
    load_raw,
    to_ac_channels,
)

# Fixed so the committed artifact is byte-reproducible from the same input.
SEED = 20260727


def build(raw: Path, *, units: int, stride: int) -> pd.DataFrame:
    frame = load_raw(raw)
    calibration = Calibration.fit(frame)

    # Longest-lived units carry the fullest degradation trajectory, which is
    # what makes a climbing score legible inside a 90-second demo.
    lifetimes = frame.groupby("unit")["cycle"].max().sort_values(ascending=False)
    chosen = list(lifetimes.index[:units])
    device_ids = {unit: f"AC-{index + 1:04d}" for index, unit in enumerate(chosen)}

    selected = frame[frame["unit"].isin(chosen)]
    selected = selected[selected["cycle"] % stride == 1]

    mapped = to_ac_channels(selected, calibration, rng=np.random.default_rng(SEED))
    mapped["device_id"] = mapped["unit"].map(device_ids)
    mapped["sequence"] = mapped.groupby("device_id").cumcount()

    # Simulator control metadata, never a model input: P4's fault injection
    # needs to know where in a unit's life each row sits so it can jump ahead.
    lifetime_by_unit = mapped.groupby("unit")["cycle"].transform("max")
    mapped["life_fraction"] = mapped["cycle"] / lifetime_by_unit

    columns = ["device_id", "sequence", *CHANNEL_COLUMNS, "life_fraction"]
    return mapped[columns].sort_values(["device_id", "sequence"]).reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=Path("data/raw/train_FD001.txt"))
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("../apps/device-simulator/data/replay_fd001.parquet"),
    )
    parser.add_argument("--units", type=int, default=4, help="devices in the demo fleet")
    parser.add_argument("--stride", type=int, default=REPLAY_STRIDE, help="keep every Nth cycle")
    args = parser.parse_args()

    fixture = build(args.raw, units=args.units, stride=args.stride)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fixture.to_parquet(args.out, index=False, compression="zstd")

    summary = fixture.groupby("device_id")["sequence"].max() + 1
    print(f"wrote {args.out} — {len(fixture)} rows")
    print(summary.to_string())


if __name__ == "__main__":
    main()
