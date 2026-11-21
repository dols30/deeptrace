"""Adapters from the existing checkpoint runners to DetectionResult.

The database stores these results. It does not import EfficientNet or AASIST.
"""

from deeptrace.ml.attribution import AASISTAudioAttribution, GradCAMVideoAttribution
from deeptrace.ml.explainers import AASISTTemporalOcclusionExplainer, EfficientNetGradCAMExplainer
from deeptrace.ml.types import DetectionResult, FindingDraft
from deeptrace.schemas import ComponentResult, MediaMetadata

THRESHOLD = 0.5


def _frame_attribution(component: ComponentResult, start_time: float) -> dict:
    if component.component == "audio" and component.coverage and component.coverage.get("mode") == "full" and start_time > 0:
        return {}  # The runner explains only its first input window.
    payload = component.attribution or {}
    frames = payload.get("frames") if isinstance(payload, dict) else None
    if not isinstance(frames, list):
        return payload if isinstance(payload, dict) else {}
    for frame in frames:
        if isinstance(frame, dict) and frame.get("start_time") == start_time:
            return frame
    return {}


def detection_from_component(
    component: ComponentResult,
    metadata: MediaMetadata,
    *,
    threshold: float | None = None,
    preprocessing_version: str,
) -> DetectionResult:
    """Map an analyzer result into findings. Aggregate scores are labeled as such."""
    if threshold is None:
        threshold = component.threshold if component.threshold is not None else THRESHOLD
    findings: list[FindingDraft] = []
    samples = []
    for sample in component.samples:
        payload = sample.model_dump()
        samples.append(payload)
        if component.aggregation_method == 'mean_frame_score' and (component.raw_score is None or component.raw_score < threshold):
            continue  # Preserve the whole-frame detector's declared mean-based review policy.
        if sample.raw_score < threshold:
            continue
        frame = _frame_attribution(component, sample.start_time)
        if component.component == "video":
            method = "gradcam" if frame.get("heatmap") else None
        else:
            if frame.get("windows"):
                method = "temporal_occlusion"
            else:
                method = "AASIST relevance" if frame and component.status == "functional" else None
        findings.append(FindingDraft(
            modality=component.component,
            start_time=sample.start_time,
            end_time=sample.end_time,
            raw_logits=sample.raw_logits,
            raw_score=sample.raw_score,
            normalized_score=None,
            calibrated_probability=None,
            threshold=threshold,
            predicted_class=sample.predicted_class,
            score_scope=sample.score_scope,
            attribution_method=method,
            attribution=frame,
        ))
    if (not findings and component.status == "functional" and component.synthetic_confidence is not None
            and not (component.task == "face_manipulation" and component.samples)):
        if component.synthetic_confidence >= threshold:
            spans = component.timestamps_seconds or [0.0]
            for start in spans:
                findings.append(FindingDraft(
                    modality=component.component,
                    start_time=start,
                    end_time=metadata.duration_seconds if not component.timestamps_seconds else start,
                    raw_logits=None,
                    raw_score=component.synthetic_confidence,
                    normalized_score=None,
                    calibrated_probability=None,
                    threshold=threshold,
                    predicted_class="possible_manipulation",
                    score_scope="aggregate" if component.timestamps_seconds else "file",
                    attribution_method=None,
                ))
    predicted = None
    if component.synthetic_confidence is not None:
        predicted = "possible_manipulation" if component.synthetic_confidence >= threshold else "no_elevated_signal"
        if component.task == "face_manipulation" and component.samples:
            predicted = "possible_manipulation" if any(s.raw_score >= threshold for s in component.samples) else "no_elevated_signal"
    return DetectionResult(
        model_name=component.model_name,
        model_version=component.model_version,
        checkpoint=component.checkpoint,
        modality=component.component,
        status=component.status,
        raw_logits=None,
        score=component.synthetic_confidence,
        calibrated_probability=None,
        calibration_version=None,
        predicted_class=predicted,
        threshold=threshold,
        preprocessing_version=preprocessing_version,
        findings=findings,
        sample_scores=samples,
        notes=list(component.notes),
        metadata={
            "development_mock": component.status == "stub" and component.model_version == "development-mock",
            "attribution": component.attribution or {},
            "coverage": component.coverage,
            "coverage_limited": any(a.code == "LIMITED_FACE_COVERAGE" for a in component.anomalies),
            "detector_id": component.detector_id,
            "task": component.task,
            "aggregation_method": component.aggregation_method,
            "threshold_source": component.threshold_source,
            "threshold_validated": component.threshold_validated,
        },
    )


class EfficientNetB4Detector:
    """Video detector adapter. explain() runs Grad-CAM when activations are supplied."""

    def __init__(self, analyzer):
        self.analyzer = analyzer

    def analyze(self, frames_dir, metadata) -> DetectionResult:
        component = self.analyzer.analyze(frames_dir, metadata)
        return detection_from_component(
            component, metadata, preprocessing_version="efficientnetb4-face-crop",
        )

    def explain(self, detection: DetectionResult) -> dict:
        stored = detection.metadata.get("attribution") or {}
        frames = stored.get("frames") if isinstance(stored, dict) else None
        if isinstance(frames, list) and frames:
            explained = [EfficientNetGradCAMExplainer().explain(frame) for frame in frames]
            return {
                "method": "gradcam",
                "modality": "video",
                "target": "fake_logit_index_1",
                "available": any(item["available"] for item in explained),
                "summary": "Highlighted areas had greater influence on this model output.",
                "artifacts": explained,
                "heatmap": explained[0].get("heatmap"),
                "limitations": explained[0].get("limitations", []),
            }
        return EfficientNetGradCAMExplainer().explain({
            "feature_maps": detection.metadata.get("feature_maps"),
            "gradients": detection.metadata.get("gradients"),
            **(stored if isinstance(stored, dict) else {}),
        })


class AASISTDetector:
    """Audio detector adapter. explain() uses adapter relevance when it exists."""

    def __init__(self, analyzer):
        self.analyzer = analyzer
        self._attribution = AASISTAudioAttribution()

    def analyze(self, audio_path, metadata) -> DetectionResult:
        component = self.analyzer.analyze(audio_path, metadata)
        return detection_from_component(component, metadata, preprocessing_version="pcm-16k-mono")

    def explain(self, detection: DetectionResult) -> dict:
        attribution = detection.metadata.get("attribution") or {}
        temporal = AASISTTemporalOcclusionExplainer().explain(attribution if isinstance(attribution, dict) else {})
        if temporal["available"]:
            return temporal
        return self._attribution.explain(
            temporal=attribution.get("temporal_relevance") if isinstance(attribution, dict) else None,
            spectral=attribution.get("spectral_relevance") if isinstance(attribution, dict) else None,
            attention=attribution.get("graph_attention") if isinstance(attribution, dict) else None,
        )


class MockVideoDetector:
    """Development stand-in. It must never be described as a model prediction."""

    model_name = "MockVideoDetector"
    model_version = "development-mock"

    def analyze(self, _frames_dir, metadata) -> DetectionResult:
        from deeptrace.schemas import ComponentResult, ModelSample
        component = ComponentResult(
            component="video", status="stub", model_name=self.model_name, model_version=self.model_version,
            synthetic_confidence=0.81,
            samples=[ModelSample(start_time=1.0, end_time=2.0, raw_score=0.81,
                predicted_class="possible_manipulation", score_scope="sample")],
            notes=["Development mock adapter. These values are not model predictions."],
        )
        return detection_from_component(component, metadata, preprocessing_version="mock")

    def explain(self, _detection: DetectionResult) -> dict:
        return GradCAMVideoAttribution().explain()


class MockAudioDetector:
    model_name = "MockAudioDetector"
    model_version = "development-mock"

    def analyze(self, _audio_path, metadata) -> DetectionResult:
        from deeptrace.schemas import ComponentResult, ModelSample
        component = ComponentResult(
            component="audio", status="stub", model_name=self.model_name, model_version=self.model_version,
            synthetic_confidence=0.66,
            samples=[ModelSample(start_time=0.0, end_time=metadata.duration_seconds, raw_score=0.66,
                predicted_class="possible_manipulation", score_scope="file")],
            notes=["Development mock adapter. These values are not model predictions."],
        )
        return detection_from_component(component, metadata, preprocessing_version="mock")

    def explain(self, _detection: DetectionResult) -> dict:
        return AASISTAudioAttribution().explain()
