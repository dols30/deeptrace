"""Model-independent explanation records.

Torch forwards stay in the inference scripts. These classes only accept
JSON-ready values the runners already computed.
"""

from deeptrace.ml.attribution import ATTRIBUTION_CAVEAT, grad_cam

VIDEO_LIMITATIONS = [
    "Highlighted areas had greater influence on this model output.",
    "The map is an 8 by 8 Grad-CAM grid on the aligned 256 pixel face, not a pixel-level finding.",
    "Attribution is not evidence that the highlighted region was manipulated.",
    "The frame map explains that frame's fake-class logit. It does not explain the mean of other frames.",
]

AUDIO_OCCLUSION_LIMITATIONS = [
    "Temporal importance is the change in the spoof screening score when a span is masked.",
    "AASIST scores the first 4.0375 seconds only. Later audio is outside the model input.",
    "A mask can be out of distribution. The fill value is part of the method.",
    "A score change is not evidence that the span was synthesized.",
]


def _base(method: str, modality: str, target: str, summary: str, limitations: list[str], *, available: bool, heatmap=None, extra: dict | None = None) -> dict:
    payload = {
        "method": method,
        "modality": modality,
        "target": target,
        "available": available,
        "summary": summary,
        "artifacts": [],
        "limitations": list(limitations),
        "caveat": ATTRIBUTION_CAVEAT,
    }
    if extra:
        payload.update(extra)
    if heatmap is not None:
        payload["heatmap"] = heatmap
        payload["artifacts"] = [{"kind": "heatmap", "heatmap": heatmap}]
    return payload


class EfficientNetGradCAMExplainer:
    """Primary video explanation. The map is Grad-CAM on EfficientNetB4.features for fake logit 1."""

    method = "gradcam"
    modality = "video"
    target = "fake_logit_index_1"

    def explain(self, attribution: dict | None) -> dict:
        payload = attribution or {}
        heatmap = payload.get("heatmap")
        if heatmap is None and payload.get("feature_maps") is not None and payload.get("gradients") is not None:
            heatmap = grad_cam(payload["feature_maps"], payload["gradients"])
        if not heatmap:
            return _base(
                self.method, self.modality, self.target,
                "Grad-CAM was not produced for this frame. The screening score stands without a map.",
                VIDEO_LIMITATIONS, available=False,
            )
        extra = {}
        for key in ("alignment", "logits", "screening_score", "sanity", "artifact_paths", "model_input_size", "crop_jpeg_base64"):
            if key in payload:
                extra[key] = payload[key]
        result = _base(
            self.method, self.modality, payload.get("target", self.target),
            "Highlighted areas had greater influence on this model output.",
            list(payload.get("limitations") or VIDEO_LIMITATIONS),
            available=True, heatmap=heatmap, extra=extra,
        )
        if payload.get("alignment"):
            result["artifacts"].append({"kind": "alignment", "alignment": payload["alignment"]})
        return result


class VideoOcclusionExplainer:
    """Validation for Grad-CAM. Not the picture shown as the investigator explanation."""

    method = "occlusion"
    modality = "video"
    target = "fake_softmax_index_1"

    def explain(self, attribution: dict | None) -> dict:
        payload = attribution or {}
        if "high_score_delta" not in payload or "low_score_delta" not in payload:
            return _base(
                self.method, self.modality, self.target,
                "Occlusion validation was not run for this frame.",
                ["Occlusion checks whether masking high-attribution regions moves the screening score more than masking low-attribution regions."],
                available=False,
            )
        return _base(
            self.method, self.modality, self.target,
            "Occlusion measured how the fake-class screening score changed when face-crop regions were masked. This validates Grad-CAM. It is not a separate claim of manipulation.",
            ["The mask fill is mid-gray in the normalized model input.", "One frame pair is a check, not a study."],
            available=True,
            extra={
                "high_score_delta": payload["high_score_delta"],
                "low_score_delta": payload["low_score_delta"],
                "high_exceeds_low": payload.get("high_exceeds_low"),
            },
        )


class AASISTTemporalOcclusionExplainer:
    """Primary audio explanation, once the runner returns signed window deltas."""

    method = "temporal_occlusion"
    modality = "audio"
    target = "spoof_softmax_index_0"

    def explain(self, attribution: dict | None) -> dict:
        payload = attribution or {}
        windows = payload.get("windows")
        if not isinstance(windows, list) or not windows:
            return _base(
                self.method, self.modality, self.target,
                "Temporal occlusion was not produced. The file-level screening score stands without a timeline.",
                AUDIO_OCCLUSION_LIMITATIONS, available=False,
            )
        extra = {"windows": windows}
        for key in (
            "parameters", "fills", "fill_rankings_agree", "displayed_fill", "repeat_padded",
            "truncated", "original_samples", "analyzed_end_seconds", "baseline_spoof_softmax",
            "integrated_gradients", "attention", "noise_scale", "logits",
        ):
            if key in payload:
                extra[key] = payload[key]
        limitations = list(AUDIO_OCCLUSION_LIMITATIONS)
        if payload.get("repeat_padded"):
            limitations.append("Samples past the original recording are repeated copies of the start.")
        if payload.get("truncated"):
            limitations.append("Audio at or after 4.0375 seconds was outside the model input.")
        result = _base(
            self.method, self.modality, self.target,
            "Masking a listed segment changed the model screening score by the stored score_delta.",
            limitations, available=True, extra=extra,
        )
        result["artifacts"] = [{"kind": "temporal_windows", "windows": windows}]
        return result


class AASISTIntegratedGradientsExplainer:
    """Secondary audio experiment. Not an investigator explanation until it is compared with occlusion."""

    method = "integrated_gradients"
    modality = "audio"
    target = "spoof_logit_index_0"

    def explain(self, attribution: dict | None = None) -> dict:
        bins = (attribution or {}).get("bins")
        if not isinstance(bins, list) or not bins:
            return _base(
                self.method, self.modality, self.target,
                "Integrated gradients have not been run for this recording.",
                ["Sample-level gradients are not shown. A later experiment must bin them and compare them with temporal occlusion."],
                available=False,
            )
        result = _base(
            self.method, self.modality, self.target,
            "Binned integrated gradients are a secondary experiment, not the investigator timeline.",
            ["Compare these bins with temporal occlusion before treating them as the explanation."],
            available=True, extra={"bins": bins},
        )
        result["artifacts"] = [{"kind": "gradient_bins", "bins": bins}]
        return result


class AASISTAttentionInspector:
    """Internal model attention. Not a causal account of the spoof score."""

    method = "graph_attention"
    modality = "audio"
    target = "internal_model_attention"

    def explain(self, attribution: dict | None) -> dict:
        maps = (attribution or {}).get("attention_maps")
        if not maps:
            return _base(
                self.method, self.modality, self.target,
                "Graph attention was not captured. It is an internal model view, not the reason for the prediction.",
                ["AASIST forward does not return attention maps.", "Graph pooling drops the original time bins."],
                available=False,
            )
        result = _base(
            self.method, self.modality, self.target,
            "Internal model attention. These weights are not a causal explanation of the screening score.",
            ["Do not read attention as proof of a synthetic span."],
            available=True, extra={"attention_maps": maps},
        )
        result["artifacts"] = [{"kind": "attention", "attention_maps": maps}]
        return result
