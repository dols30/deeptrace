import json
import sys
from pathlib import Path

from deeptrace.analyzers.video import EfficientNetVideoAnalyzer
from deeptrace.ml.detectors import EfficientNetB4Detector, detection_from_component
from deeptrace.ml.explainers import (
    AASISTAttentionInspector,
    AASISTIntegratedGradientsExplainer,
    AASISTTemporalOcclusionExplainer,
    EfficientNetGradCAMExplainer,
    VideoOcclusionExplainer,
)
from deeptrace.schemas import ComponentResult, MediaMetadata, ModelSample
from deeptrace.workflow.service import _explain


def test_gradcam_explainer_uses_the_runner_heatmap_and_does_not_claim_manipulation():
    result = EfficientNetGradCAMExplainer().explain({
        "heatmap": [[0.0, 1.0], [0.25, 0.0]],
        "alignment": {"matrix": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], "crop_size": 256},
        "logits": [0.2, 1.4],
    })
    assert result["available"] is True
    assert result["method"] == "gradcam"
    assert result["target"] == "fake_logit_index_1"
    assert result["heatmap"][0][1] == 1.0
    assert result["alignment"]["crop_size"] == 256
    assert "manipulat" not in result["summary"].lower()
    assert _explain("video", {"heatmap": [[0.0, 1.0], [0.0, 0.0]]})["heatmap"][0][1] == 1.0


def test_gradcam_without_a_map_stays_unavailable():
    result = EfficientNetGradCAMExplainer().explain({})
    assert result["available"] is False
    assert "heatmap" not in result


def test_other_explainers_keep_their_roles():
    occlusion = VideoOcclusionExplainer().explain({"high_score_delta": 0.2, "low_score_delta": 0.01, "high_exceeds_low": True})
    assert occlusion["available"] is True
    assert occlusion["method"] == "occlusion"
    windows = AASISTTemporalOcclusionExplainer().explain({"windows": [{"start": 0.0, "end": 0.5, "score_delta": 0.17}]})
    assert windows["windows"][0]["score_delta"] == 0.17
    assert AASISTIntegratedGradientsExplainer().explain({})["available"] is False
    attention = AASISTAttentionInspector().explain({"attention_maps": {"GAT_layer_T": [1, 29, 29, 1]}})
    assert "not a causal explanation" in attention["summary"]


def test_video_adapter_keeps_gradcam_on_the_matching_frame(tmp_path: Path):
    bridge = tmp_path / "bridge.py"
    payload = {
        "model_version": "efficientnetb4@test",
        "checkpoint": "effnb4_best.pth#sha256=abc",
        "samples": [{
            "path": "frame_000001.jpg",
            "fake_probability": 0.81,
            "logits": [0.1, 1.5],
            "attribution": {
                "method": "gradcam",
                "heatmap": [[0.0, 1.0], [0.0, 0.0]],
                "alignment": {"matrix": [[1, 0, 3], [0, 1, 4]], "frame_width": 640, "frame_height": 480, "crop_size": 256},
                "target": "fake_logit_index_1",
            },
        }],
    }
    bridge.write_text("import json; print(json.dumps(" + json.dumps(payload) + "))")
    metadata = MediaMetadata(filename="clip.mp4", media_kind="video", content_type="video/mp4", size_bytes=4, sha256="a" * 64)
    component = EfficientNetVideoAnalyzer(f"{sys.executable} {bridge} --frames {{frames_dir}}", 1.0).analyze(tmp_path, metadata)
    assert component.attribution["frames"][0]["heatmap"][0][1] == 1.0
    assert component.attribution["frames"][0]["alignment"]["matrix"][0][2] == 3
    assert component.samples[0].raw_logits == [0.1, 1.5]
    detection = detection_from_component(component, metadata, preprocessing_version="efficientnetb4-face-crop")
    assert detection.findings[0].attribution_method == "gradcam"
    assert detection.findings[0].attribution["heatmap"][0][1] == 1.0
    explained = EfficientNetB4Detector(None).explain(detection)
    assert explained["available"] is True
    assert explained["heatmap"][0][1] == 1.0


def test_video_without_a_map_does_not_claim_gradcam():
    metadata = MediaMetadata(filename="clip.mp4", media_kind="video", content_type="video/mp4", size_bytes=4, sha256="b" * 64)
    component = ComponentResult(
        component="video", status="functional", model_name="DeepfakeBench EfficientNet-B4", model_version="test",
        synthetic_confidence=0.8, samples=[ModelSample(
            start_time=0.0, end_time=1.0, raw_score=0.8, predicted_class="possible_manipulation", score_scope="sample",
        )],
    )
    detection = detection_from_component(component, metadata, preprocessing_version="efficientnetb4-face-crop")
    assert detection.findings[0].attribution_method is None
    assert EfficientNetB4Detector(None).explain(detection)["available"] is False
