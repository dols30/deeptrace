"""Grad-CAM sanity checks that do not need the checkpoint.

The multi-face run lives in scripts/dev/validate_gradcam.py and is executed
when the model virtualenv and weights are present.
"""
import json
import os
import subprocess
import urllib.request
from pathlib import Path

import pytest

from deeptrace.ml.attribution import grad_cam
from deeptrace.ml.explainers import EfficientNetGradCAMExplainer

ROOT = Path(__file__).resolve().parents[2]
WEIGHTS = ROOT / "models/efficientnetb4/effnb4_best.pth"
LANDMARKS = ROOT / "models/efficientnetb4/shape_predictor_81_face_landmarks.dat"
REPO = ROOT / "vendor/DeepfakeBench"
MODEL_PYTHON = ROOT / ".venv-models/bin/python"
FACES = [
    "2007_007763.jpg",
    "2008_001322.jpg",
    "2008_002470.jpg",
    "2009_004587.jpg",
]


def test_gradcam_changes_when_the_activations_change():
    first = grad_cam([[[0, 1], [0, 0]], [[0, 0], [0, 0]]], [[[1, 1], [0, 0]], [[0, 0], [0, 0]]])
    second = grad_cam([[[0, 0], [1, 0]], [[0, 0], [0, 0]]], [[[0, 0], [1, 1]], [[0, 0], [0, 0]]])
    assert first != second
    assert first[0][1] == 1
    assert second[1][0] == 1


def test_gradcam_changes_when_the_gradient_target_changes():
    features = [[[1, 0], [0, 0]], [[0, 1], [0, 0]]]
    toward_first = grad_cam(features, [[[1, 0], [0, 0]], [[0, 0], [0, 0]]])
    toward_second = grad_cam(features, [[[0, 0], [0, 0]], [[0, 1], [0, 0]]])
    assert toward_first != toward_second


def test_explainer_keeps_the_face_crop_for_the_viewer():
    result = EfficientNetGradCAMExplainer().explain({
        "heatmap": [[1.0]],
        "crop_jpeg_base64": "abc",
        "screening_score": 0.81,
    })
    assert result["crop_jpeg_base64"] == "abc"
    assert result["screening_score"] == 0.81
    assert "manipulat" not in result["summary"].lower()


@pytest.mark.skipif(
    not (MODEL_PYTHON.is_file() and WEIGHTS.is_file() and LANDMARKS.is_file() and REPO.is_dir())
    or os.environ.get("DEEPTRACE_RUN_EXPLAIN_VALIDATION") != "1",
    reason="Set DEEPTRACE_RUN_EXPLAIN_VALIDATION=1 to score multiple faces with the local checkpoint.",
)
def test_checkpoint_gradcam_on_multiple_faces(tmp_path: Path):
    images = []
    for name in FACES:
        destination = tmp_path / name
        url = "https://raw.githubusercontent.com/davisking/dlib/master/examples/faces/" + name
        urllib.request.urlretrieve(url, destination)
        images.append(destination)
    script = ROOT / "scripts/dev/validate_gradcam.py"
    completed = subprocess.run(
        [str(MODEL_PYTHON), str(script), "--repo", str(REPO), "--weights", str(WEIGHTS),
         "--landmarks", str(LANDMARKS), "--images", *map(str, images), "--device", "cpu"],
        capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    report = json.loads(completed.stdout)
    assert report["scored_faces"] >= 2
    assert report["target_class_changes_map"] is True
    assert report["maps_differ_across_faces"] is True
    assert report["occlusion_high_exceeds_low"] + report["occlusion_high_does_not_exceed_low"] == report["scored_faces"]
