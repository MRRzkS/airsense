"""In-process ONNX scoring.

A separate model service is the right production answer and the wrong MVP
answer; see docs/architecture.md. The cost of this choice is recorded here: the
feature window lives in this process's memory, so scores are lost on restart and
a second replica would start cold and disagree with the first until both warmed
up.
"""

import json
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import onnxruntime as ort
import structlog

from airsense.domain.features import WINDOW_SIZE, build_feature_vector
from airsense.domain.telemetry import SensorReading

log = structlog.get_logger("scoring")


@dataclass(slots=True)
class NullScorer:
    """Used when no model artifact is present. Never scores anything."""

    def score(self, reading: SensorReading) -> float | None:
        return None


@dataclass(slots=True)
class OnnxDegradationScorer:
    session: ort.InferenceSession
    input_name: str
    _windows: dict[str, deque[SensorReading]] = field(default_factory=dict, init=False)

    def score(self, reading: SensorReading) -> float | None:
        window = self._windows.setdefault(reading.device_id.value, deque(maxlen=WINDOW_SIZE))
        window.append(reading)
        if len(window) < WINDOW_SIZE:
            return None

        features = np.array([build_feature_vector(list(window))], dtype=np.float32)
        # Synchronous on the event loop: this model is ~100 KB and scores a
        # single row in well under a millisecond. At a fleet size where that
        # stops holding, it moves to a thread pool or out of process entirely.
        raw = self.session.run(None, {self.input_name: features})[0]
        # A regressor can overshoot its training range; the domain defines a
        # health index as a fraction, so the clamp belongs here rather than
        # leaving ScoredReading to reject the model's own output.
        return min(max(float(np.asarray(raw).ravel()[0]), 0.0), 1.0)


def create_scorer(model_path: Path, spec_path: Path) -> OnnxDegradationScorer | NullScorer:
    """Load the exported model, or fall back to scoring nothing.

    A missing artifact degrades to unscored telemetry rather than refusing to
    start: the pipe is still worth running, and the log says why the chart has
    no score line.
    """
    if not model_path.exists() or not spec_path.exists():
        log.error(
            "model.missing",
            model=str(model_path),
            spec=str(spec_path),
            hint="run ml/train.py",
        )
        return NullScorer()

    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    if spec["window_size"] != WINDOW_SIZE:
        raise ValueError(
            f"model expects a {spec['window_size']}-sample window, domain builds {WINDOW_SIZE}"
        )

    session = ort.InferenceSession(model_path.read_bytes(), providers=["CPUExecutionProvider"])
    log.info("model.loaded", model=str(model_path), features=len(spec["features"]))
    return OnnxDegradationScorer(session=session, input_name=spec["input_name"])
