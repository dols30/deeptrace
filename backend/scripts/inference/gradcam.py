"""Grad-CAM for the DeepfakeBench EfficientNet-B4 feature map.

The map is the tensor returned by EfficientNetB4.features, which is the
post-Swish activation that adaptive average pooling reads. The attributed
scalar is fake logit index 1. Callers must not wrap this pass in
torch.inference_mode.
"""
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

LIMITATIONS = [
    "Highlighted areas had greater influence on this model output.",
    "The map is an 8 by 8 Grad-CAM grid on the aligned 256 pixel face, not a pixel-level finding.",
    "Attribution is not evidence that the highlighted region was manipulated.",
    "The frame map explains that frame's fake-class logit. It does not explain the mean of other frames.",
]


def _as_lists(array, places=6):
    values = np.asarray(array, dtype=np.float64)
    if values.ndim == 1:
        return [round(float(value), places) for value in values]
    return [_as_lists(value, places) for value in values]


def grad_cam_map(features, gradients):
    """Channel-weighted Grad-CAM. features and gradients are (1, C, H, W)."""
    weights = gradients.mean(dim=(2, 3))
    combined = torch.relu((features * weights[:, :, None, None]).sum(dim=1))[0]
    peak = combined.max()
    if float(peak) > 0:
        combined = combined / peak
    return combined.detach()


def explain_tensor(model, tensor, target=1):
    """Return logits (1, 2) and an 8x8 map. tensor is (1, 3, 256, 256)."""
    model.zero_grad(set_to_none=True)
    features = model.features(tensor)
    features.retain_grad()
    logits = model.classifier(features)
    if tuple(logits.shape) != (1, 2):
        raise ValueError("Expected two FF++ logits")
    logits[0, target].backward()
    if features.grad is None:
        raise RuntimeError("Gradients did not reach EfficientNetB4.features")
    heatmap = grad_cam_map(features.detach(), features.grad.detach())
    return logits.detach(), heatmap


def resize_map(heatmap, size):
    scaled = F.interpolate(heatmap[None, None], size=(size, size), mode="bilinear", align_corners=False)
    return scaled[0, 0]


def _region_delta(model, tensor, heatmap, index):
    cells = heatmap.shape[0]
    step = tensor.shape[-1] // cells
    row, col = divmod(index, cells)
    masked = tensor.detach().clone()
    masked[:, :, row * step:(row + 1) * step, col * step:(col + 1) * step] = 0
    with torch.inference_mode():
        logits = model(masked)
        score = torch.softmax(logits, dim=1)[0, 1]
    return float(score)


def occlusion_check(model, tensor, heatmap, baseline_score):
    """Mask the strongest and weakest Grad-CAM cells. Fill 0 is mid-gray in pixel space."""
    flat = heatmap.detach().reshape(-1)
    high = int(torch.argmax(flat))
    low = int(torch.argmin(flat))
    if float(flat[high]) == float(flat[low]):
        return {"compared": False, "reason": "uniform map", "fill": "normalized_zero_mid_gray"}
    high_score = _region_delta(model, tensor, heatmap, high)
    low_score = _region_delta(model, tensor, heatmap, low)
    high_delta = baseline_score - high_score
    low_delta = baseline_score - low_score
    cells = int(heatmap.shape[0])
    return {
        "compared": True,
        "fill": "normalized_zero_mid_gray",
        "high_index": [high // cells, high % cells],
        "low_index": [low // cells, low % cells],
        "high_score_delta": round(high_delta, 6),
        "low_score_delta": round(low_delta, 6),
        "high_exceeds_low": high_delta > low_delta,
    }


def write_overlays(directory, stem, crop_bgr, heatmap, frame_bgr, matrix):
    import cv2
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    heat = resize_map(heatmap, crop_bgr.shape[0]).cpu().numpy()
    heat_u8 = np.clip(heat * 255.0, 0, 255).astype(np.uint8)
    color = cv2.applyColorMap(heat_u8, cv2.COLORMAP_JET)
    overlay = cv2.addWeighted(crop_bgr, 0.55, color, 0.45, 0)
    crop_path = directory / f"{stem}_crop.jpg"
    attribution_path = directory / f"{stem}_attribution.jpg"
    frame_path = directory / f"{stem}_frame.jpg"
    cv2.imwrite(str(crop_path), crop_bgr)
    cv2.imwrite(str(attribution_path), overlay)
    inverse = cv2.invertAffineTransform(np.asarray(matrix, dtype=np.float64))
    height, width = frame_bgr.shape[:2]
    painted = cv2.warpAffine(color, inverse, (width, height))
    mask = cv2.warpAffine(np.full(color.shape[:2], 255, np.uint8), inverse, (width, height))
    blended = frame_bgr.copy()
    keep = mask > 0
    blended[keep] = cv2.addWeighted(frame_bgr, 0.55, painted, 0.45, 0)[keep]
    cv2.imwrite(str(frame_path), blended)
    return {
        "crop": str(crop_path),
        "attribution_overlay": str(attribution_path),
        "frame_overlay": str(frame_path),
    }


def crop_jpeg_base64(crop_bgr):
    import base64
    import cv2
    ok, encoded = cv2.imencode(".jpg", crop_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
    if not ok:
        raise RuntimeError("Could not encode the analyzed face crop")
    return base64.b64encode(encoded.tobytes()).decode("ascii")


def attribution_record(model, tensor, aligned, frame_bgr, explain_dir, stem, sanity=False):
    """Grad-CAM for one normalized face tensor, plus the alignment that locates it."""
    logits, heatmap = explain_tensor(model, tensor, target=1)
    score = float(torch.softmax(logits, dim=1)[0, 1])
    record = {
        "method": "gradcam",
        "modality": "video",
        "target": "fake_logit_index_1",
        "heatmap": _as_lists(heatmap.cpu().numpy()),
        "model_input_size": int(tensor.shape[-1]),
        "screening_score": round(score, 6),
        "logits": _as_lists(logits[0].cpu().numpy()),
        "limitations": list(LIMITATIONS),
        "alignment": {
            "matrix": _as_lists(aligned["matrix"]),
            "source_landmarks": _as_lists(aligned["landmarks"]),
            "frame_width": aligned["frame_width"],
            "frame_height": aligned["frame_height"],
            "crop_size": aligned["crop_size"],
        },
        "crop_jpeg_base64": crop_jpeg_base64(aligned["crop"]),
    }
    if explain_dir is not None:
        record["artifact_paths"] = write_overlays(
            explain_dir, stem, aligned["crop"], heatmap, frame_bgr, aligned["matrix"],
        )
    if sanity:
        _, other = explain_tensor(model, tensor, target=0)
        record["sanity"] = {
            "target_class_changes_map": bool(torch.max(torch.abs(heatmap - other)) > 1e-4),
            "occlusion": occlusion_check(model, tensor, heatmap, score),
        }
    return record, logits, score
