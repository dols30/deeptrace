import sys
from pathlib import Path

from deeptrace.analyzers.audio import AASISTAudioAnalyzer
from deeptrace.ml.assistant import RulesCaseAssistant
from deeptrace.ml.detectors import AASISTDetector, detection_from_component
from deeptrace.ml.explainers import AASISTTemporalOcclusionExplainer
from deeptrace.schemas import MediaMetadata

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "inference"))
from audio_explain import (  # noqa: E402
    ANALYZED_SAMPLES,
    bin_attributions,
    mask_span,
    overlap_record,
    rankings_agree,
    window_starts,
)


def test_windows_cover_the_analyzed_span_and_the_tail():
    starts = window_starts()
    assert starts[0] == 0
    assert 56000 in starts
    assert starts[-1] == ANALYZED_SAMPLES - 8000
    assert all(start + 8000 <= ANALYZED_SAMPLES for start in starts)


class _Wave:
    def __init__(self, values):
        self.values = list(values)

    def copy(self):
        return _Wave(self.values)

    def __getitem__(self, item):
        if isinstance(item, slice):
            return _Span(self.values[item])
        return self.values[item]

    def __setitem__(self, item, value):
        if isinstance(value, _Span):
            self.values[item] = list(value.values)
        elif hasattr(value, "__iter__") and not isinstance(value, (str, bytes)):
            self.values[item] = list(value)
        else:
            self.values[item] = [value] * len(self.values[item])


class _Span:
    def __init__(self, values):
        self.values = list(values)

    def mean(self):
        return sum(self.values) / len(self.values)

    def __eq__(self, other):
        return self.values[0] == other


def test_signed_deltas_keep_their_sign_when_fills_disagree():
    samples = _Wave([0.2, 0.0, 1.0, 0.1])
    zeros = mask_span(samples, 1, 3, "zeros", None)
    local = mask_span(samples, 1, 3, "local_mean", None)
    assert zeros.values[1] == 0 and zeros.values[2] == 0
    assert local.values[1] == local.values[2] == 0.5
    assert rankings_agree([[0.2, 0.1], [0.2, 0.1]]) is True
    assert rankings_agree([[0.4, 0.1, -0.2], [0.1, 0.4, -0.2]], count=1) is False
    bins = bin_attributions([0.5, -0.25], sample_rate=2, bin_samples=2)
    assert bins[0]["signed"] == 0.25
    assert bins[0]["absolute"] == 0.75
    compared = overlap_record([0.2, 0.9], [0.1, 0.8], [0, 4000], "zeros", "local_mean")
    assert compared["top_sets_match"] is True


def test_audio_adapter_keeps_signed_windows_without_calling_them_proof(tmp_path: Path):
    bridge = tmp_path / "bridge.py"
    payload = {
        "model_version": "aasist@test",
        "checkpoint": "AASIST.pth#sha256=abc",
        "fake_probability": 0.81,
        "logits": [1.2, -0.4],
        "attribution": {
            "windows": [{"start": 0.0, "end": 0.5, "score_delta": -0.17, "fill": "local_mean"}],
            "displayed_fill": "local_mean",
            "fill_rankings_agree": False,
            "repeat_padded": True,
        },
    }
    bridge.write_text("import json\nprint(json.dumps(" + repr(payload) + "))\n")
    metadata = MediaMetadata(filename="clip.wav", media_kind="audio", content_type="audio/wav", size_bytes=4, sha256="a" * 64, duration_seconds=2)
    component = AASISTAudioAnalyzer(f"{sys.executable} {bridge} --audio {{audio_path}}").analyze(tmp_path / "clip.wav", metadata)
    assert component.attribution["windows"][0]["score_delta"] == -0.17
    detection = detection_from_component(component, metadata, preprocessing_version="pcm-16k-mono")
    assert detection.findings[0].attribution_method == "temporal_occlusion"
    explained = AASISTDetector(None).explain(detection)
    assert explained["available"] is True
    assert explained["windows"][0]["score_delta"] == -0.17
    assert explained["fill_rankings_agree"] is False
    assert "repeat" in " ".join(explained["limitations"]).lower()
    assert "synthes" not in explained["summary"].lower()
    direct = AASISTTemporalOcclusionExplainer().explain(component.attribution)
    assert direct["repeat_padded"] is True


def test_assistant_quotes_the_stored_window_and_refuses_proof():
    assistant = RulesCaseAssistant()
    context = {"findings": [{
        "id": "finding-1", "modality": "audio", "start_time": 0, "end_time": 2, "raw_score": 0.81,
        "windows": [{"start": 1.0, "end": 1.5, "score_delta": 0.17, "fill": "local_mean"}],
        "fill_rankings_agree": False,
    }]}
    answer = assistant.answer("Which segment influenced the AASIST score?", context)
    assert "1.000s–1.500s" in answer["answer"]
    assert "0.170" in answer["answer"]
    assert "not evidence" in answer["answer"]
    assert answer["citations"][0]["finding_id"] == "finding-1"
    missing = assistant.answer("Show the occlusion timeline", {"findings": []})
    assert "not produced" in missing["answer"]
