import json
import math
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

import pytest

from deeptrace.analyzers.video import EfficientNetVideoAnalyzer, SceneVideoAnalyzer
from deeptrace.config import Settings
from deeptrace.ml.decision_rules import EFFICIENTNET_POC_RULE, EFFICIENTNET_POC_THRESHOLD
from deeptrace.ml.detectors import detection_from_component
from deeptrace.reporting import build_report
from deeptrace.schemas import MediaMetadata


def face_payload(scores):
    return {
        "model_version": "efficientnetb4@f188b1c105465e2e5377eb536a95022ae0e4522d",
        "checkpoint": "effnb4_best.pth#sha256=74cbd82d7be1bf5e6adec717824274a95b4509b02e1e78401608d32b3cbeaf0f",
        "notes": ["Landmarks: shape_predictor_81_face_landmarks.dat#sha256=8cae4375589dd915d9a0a881101bed1bbb4e9887e35e63b024388f1ca25ff869"],
        "samples": [{"path": f"frame_{i:06d}.jpg", "fake_probability": score} for i,score in enumerate(scores,1)],
    }


def media():
    return MediaMetadata(filename="face.mp4", media_kind="video", content_type="video/mp4", size_bytes=1, sha256="0"*64)


def score_payload(payload, rule=EFFICIENTNET_POC_RULE):
    analyzer = EfficientNetVideoAnalyzer("fake --frames {frames_dir}", decision_rule=rule)
    with patch("deeptrace.analyzers.video.subprocess.run", return_value=CompletedProcess([],0,json.dumps(payload),"")):
        return analyzer.analyze(Path("frames"),media())


@pytest.mark.parametrize("high,flagged", [
    (math.nextafter(EFFICIENTNET_POC_THRESHOLD,0),False),
    (EFFICIENTNET_POC_THRESHOLD,True),
    (math.nextafter(EFFICIENTNET_POC_THRESHOLD,1),True),
])
def test_poc_any_frame_rule_matches_observations_samples_findings_and_summary(high,flagged):
    component = score_payload(face_payload([.1,high]))
    assert component.status == "functional"
    assert component.threshold == EFFICIENTNET_POC_THRESHOLD
    assert component.raw_score < component.threshold  # Any-frame policy, not a mean-score decision.
    assert component.timestamps_seconds == ([1.] if flagged else [])
    assert bool(component.anomalies) == flagged
    assert component.samples[-1].predicted_class == ("possible_manipulation" if flagged else "no_elevated_signal")
    result = detection_from_component(component,media(),preprocessing_version="test")
    assert result.threshold == component.threshold
    assert bool(result.findings) == flagged
    assert result.predicted_class == component.samples[-1].predicted_class
    assert all(f.threshold == component.threshold for f in result.findings)
    assert result.metadata["threshold_source"] == component.threshold_source
    assert component.calibrated_probability is None and not component.threshold_validated
    report = build_report(media(),[component])
    assert bool(report.anomalies) == flagged
    assert "0.5 development/default" not in " ".join(report.methods)


def test_below_rule_mean_is_not_rounded_into_false_positive():
    high = math.nextafter(EFFICIENTNET_POC_THRESHOLD,0)
    component = score_payload(face_payload([high,high]))
    assert component.raw_score == high
    assert not component.anomalies
    assert not detection_from_component(component,media(),preprocessing_version="test").findings


@pytest.mark.parametrize("field", ["checkpoint","model_version","notes"])
def test_poc_rule_fails_closed_for_different_model_provenance(field):
    payload = face_payload([1.])
    payload[field] = [] if field == "notes" else "different"
    component = score_payload(payload)
    assert component.status == "error" and component.raw_score is None


def test_default_face_and_scene_rules_remain_0_5():
    assert score_payload(face_payload([.8]),"default_0_5").timestamps_seconds == [0.]
    analyzer = SceneVideoAnalyzer("fake --frames {frames_dir}")
    with patch("deeptrace.analyzers.video.subprocess.run", return_value=CompletedProcess([],0,json.dumps(face_payload([.8])),"")):
        component = analyzer.analyze(Path("frames"),media())
    assert component.threshold == .5 and component.timestamps_seconds == [0.]


def test_poc_setting_is_opt_in_and_locks_sampling_policy():
    assert Settings(_env_file=None).efficientnet_decision_rule == "default_0_5"
    assert Settings(_env_file=None,efficientnet_decision_rule=EFFICIENTNET_POC_RULE).max_frames == 120
    for changes in ({"frame_interval_seconds":2.},{"max_frames":30},{"efficientnet_decision_rule":"arbitrary"}):
        with pytest.raises(ValueError):
            Settings(_env_file=None,**{"efficientnet_decision_rule":EFFICIENTNET_POC_RULE,**changes})
