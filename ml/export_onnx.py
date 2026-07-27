"""scikit-learn to ONNX conversion."""

from pathlib import Path
from typing import Final

import numpy as np
import onnxruntime as ort
import pandas as pd
from skl2onnx import convert_sklearn
from skl2onnx.common.data_types import FloatTensorType
from sklearn.pipeline import Pipeline

INPUT_NAME: Final = "features"

# Pinned rather than left to default: the runtime in the ingest image must be
# able to load what this writes, and letting the exporter pick the newest opset
# it knows about is how that silently breaks on a version bump.
TARGET_OPSET: Final = 17


def export(model: Pipeline, feature_count: int, destination: Path) -> None:
    onnx_model = convert_sklearn(
        model,
        initial_types=[(INPUT_NAME, FloatTensorType([None, feature_count]))],
        target_opset=TARGET_OPSET,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(onnx_model.SerializeToString())


def verify(model: Pipeline, sample: pd.DataFrame, destination: Path) -> float:
    """Score `sample` through both sklearn and the exported graph.

    Returns the largest absolute disagreement. Conversion can quietly change
    behaviour — float64 to float32, unsupported ops silently approximated — so
    the export is not trusted until it has been run.
    """
    session = ort.InferenceSession(destination.read_bytes(), providers=["CPUExecutionProvider"])
    onnx_out = session.run(None, {INPUT_NAME: sample.to_numpy(dtype=np.float32)})[0]
    sklearn_out = model.predict(sample)
    return float(np.max(np.abs(np.asarray(onnx_out).ravel() - sklearn_out.ravel())))
