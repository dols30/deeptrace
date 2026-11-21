"""Attribution providers.

A heatmap or relevance trace shows what influenced a prediction. It does not
locate manipulation and it is not proof.
"""

from typing import Protocol

ATTRIBUTION_CAVEAT = (
    "Model attribution indicates regions or segments that influenced the prediction. "
    "It is not forensic localization of manipulation."
)


def grad_cam(feature_maps: list[list[list[float]]], gradients: list[list[list[float]]]) -> list[list[float]]:
    """Grad-CAM over a late convolutional map. Channels x height x width."""
    if not feature_maps or len(feature_maps) != len(gradients):
        raise ValueError("Grad-CAM requires matching feature maps and gradients")
    height = len(feature_maps[0])
    width = len(feature_maps[0][0]) if height else 0
    weights: list[float] = []
    for channel, gradient in zip(feature_maps, gradients):
        total = sum(value for row in gradient for value in row)
        weights.append(total / (height * width))
    cam = [[0.0 for _ in range(width)] for _ in range(height)]
    for weight, channel in zip(weights, feature_maps):
        for y, row in enumerate(channel):
            for x, value in enumerate(row):
                cam[y][x] += weight * value
    peak = 0.0
    for y, row in enumerate(cam):
        for x, value in enumerate(row):
            cam[y][x] = max(0.0, value)
            peak = max(peak, cam[y][x])
    if peak == 0:
        return cam
    return [[value / peak for value in row] for row in cam]


def normalize_series(values: list[float]) -> list[float]:
    if not values:
        return []
    peak = max(abs(value) for value in values) or 1.0
    return [abs(value) / peak for value in values]


class VideoAttributionProvider(Protocol):
    method_name: str

    def explain(self, *, feature_maps=None, gradients=None) -> dict: ...


class AudioAttributionProvider(Protocol):
    method_name: str

    def explain(self, *, temporal=None, spectral=None, attention=None) -> dict: ...


class GradCAMVideoAttribution:
    """Initial video attribution method. Later methods can sit behind the same provider."""

    method_name = "Grad-CAM"

    def explain(self, *, feature_maps=None, gradients=None) -> dict:
        if feature_maps is None or gradients is None:
            return {
                "method": self.method_name,
                "available": False,
                "summary": (
                    "Grad-CAM needs the activations and gradients from the late convolutional layer. "
                    "The current checkpoint adapter returns scores only, so no heatmap was produced."
                ),
                "caveat": ATTRIBUTION_CAVEAT,
            }
        heatmap = grad_cam(feature_maps, gradients)
        return {
            "method": self.method_name,
            "available": True,
            "heatmap": heatmap,
            "summary": "Normalized Grad-CAM relevance for the analyzed face crop.",
            "caveat": ATTRIBUTION_CAVEAT,
        }


class AASISTAudioAttribution:
    """Temporal, spectral, and attention views. Attention weights are not treated as causes."""

    method_name = "AASIST relevance"

    def explain(self, *, temporal=None, spectral=None, attention=None) -> dict:
        views = {}
        if isinstance(temporal, list) and temporal:
            views["temporal_importance"] = normalize_series([float(value) for value in temporal])
        if isinstance(spectral, list) and spectral:
            views["spectral_relevance"] = spectral
        if isinstance(attention, list) and attention:
            views["graph_attention"] = attention
        if not views:
            return {
                "method": self.method_name,
                "available": False,
                "summary": (
                    "AASIST attribution was not returned by the checkpoint adapter. "
                    "File-level screening completed without a segment or spectrum map."
                ),
                "caveat": ATTRIBUTION_CAVEAT,
                "note": "Internal attention weights are not a causal explanation.",
            }
        return {
            "method": self.method_name,
            "available": True,
            "views": views,
            "summary": "Relevance values from the audio adapter. They are not a causal explanation.",
            "caveat": ATTRIBUTION_CAVEAT,
            "note": "Do not equate graph attention weights with proof of manipulation.",
        }
