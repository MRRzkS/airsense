"""The real exported model, loaded and run.

Not a mock. If the committed artifact is corrupt, built for the wrong opset, or
expects a different feature order, these fail.
"""

import json
import shutil
from pathlib import Path

import pytest

from airsense.domain.features import WINDOW_SIZE
from airsense.domain.telemetry import SensorReading
from airsense.infrastructure.onnx.scorer import NullScorer, OnnxDegradationScorer, create_scorer
from tests.fakes import make_reading

ARTIFACTS = Path(__file__).parents[4] / "ml" / "artifacts"
MODEL = ARTIFACTS / "compressor_degradation.onnx"
SPEC = ARTIFACTS / "feature_spec.json"

pytestmark = pytest.mark.skipif(not MODEL.exists(), reason="model artifacts not built")

# The extremes of the mapped operating envelope: a unit fresh from the factory
# versus one at the modelled point of failure.
HEALTHY = {
    "compressor_current_a": 4.3,
    "discharge_pressure_kpa": 2840.0,
    "suction_temperature_c": 6.1,
    "vibration_rms_mm_s": 0.9,
}
WORN = {
    "compressor_current_a": 7.7,
    "discharge_pressure_kpa": 1960.0,
    "suction_temperature_c": 12.9,
    "vibration_rms_mm_s": 6.4,
}


@pytest.fixture
def scorer() -> OnnxDegradationScorer:
    loaded = create_scorer(MODEL, SPEC)
    assert isinstance(loaded, OnnxDegradationScorer)
    return loaded


def feed(
    scorer: OnnxDegradationScorer,
    channels: dict[str, float],
    *,
    device_id: str = "AC-0001",
    count: int = WINDOW_SIZE,
) -> float | None:
    result: float | None = None
    for sequence in range(count):
        reading: SensorReading = make_reading(device_id, sequence=sequence, **channels)
        result = scorer.score(reading)
    return result


def test_no_score_until_the_window_is_full(scorer: OnnxDegradationScorer) -> None:
    for sequence in range(WINDOW_SIZE - 1):
        assert scorer.score(make_reading(sequence=sequence, **HEALTHY)) is None


def test_scores_once_the_window_fills(scorer: OnnxDegradationScorer) -> None:
    assert feed(scorer, HEALTHY) is not None


def test_score_is_a_fraction(scorer: OnnxDegradationScorer) -> None:
    for channels in (HEALTHY, WORN):
        score = feed(scorer, channels, device_id="AC-0001")
        assert score is not None
        assert 0.0 <= score <= 1.0


def test_a_worn_unit_scores_higher_than_a_healthy_one(scorer: OnnxDegradationScorer) -> None:
    # The behavioural claim the whole product rests on. If this inverts, the
    # mapping, the label or the export is wrong.
    healthy = feed(scorer, HEALTHY, device_id="AC-0001")
    worn = feed(scorer, WORN, device_id="AC-0002")

    assert healthy is not None and worn is not None
    assert worn > healthy


def test_windows_do_not_leak_between_devices(scorer: OnnxDegradationScorer) -> None:
    # One device's history must not contaminate another's features; a shared
    # window would make a single failing unit drag the whole fleet's scores up.
    feed(scorer, WORN, device_id="AC-0002", count=WINDOW_SIZE)

    for sequence in range(WINDOW_SIZE - 1):
        assert scorer.score(make_reading("AC-0003", sequence=sequence, **HEALTHY)) is None


def test_missing_artifacts_degrade_to_scoring_nothing(tmp_path: Path) -> None:
    loaded = create_scorer(tmp_path / "absent.onnx", tmp_path / "absent.json")

    assert isinstance(loaded, NullScorer)
    assert loaded.score(make_reading()) is None


def test_a_spec_disagreeing_on_window_size_is_refused(tmp_path: Path) -> None:
    # Loading anyway would feed the model a vector of the wrong length, which
    # onnxruntime reports as a shape error far from the actual cause.
    shutil.copy(MODEL, tmp_path / "model.onnx")
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    spec["window_size"] = WINDOW_SIZE + 1
    (tmp_path / "spec.json").write_text(json.dumps(spec), encoding="utf-8")

    with pytest.raises(ValueError, match="window"):
        create_scorer(tmp_path / "model.onnx", tmp_path / "spec.json")
