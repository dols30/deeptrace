"""JSON bridge around the official FakeSTormer release.

Run this only inside the isolated FakeSTormer CUDA environment. It imports the
official model/config code rather than copying the architecture into DeepTrace.
"""
from __future__ import annotations

import argparse, hashlib, json, sys, time
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--video", type=Path, required=True)
    args = parser.parse_args()
    for path in (args.repo, args.config, args.checkpoint, args.video):
        if not path.exists(): raise FileNotFoundError(path)

    sys.path.insert(0, str(args.repo.resolve()))
    import cv2, numpy as np, torch
    from PIL import Image
    from retinaface.pre_trained_models import get_model
    from configs.get_config import load_config
    from models import MODELS, build_model, load_pretrained
    from package_utils.transform import final_transform

    if not torch.cuda.is_available():
        raise RuntimeError("Official FakeSTormer inference requires a CUDA GPU")
    cfg = load_config(str(args.config))
    expected = int(cfg.DATASET.DATA.SAMPLES_PER_VIDEO.NUM_FRAMES)
    if expected != int(cfg.MODEL.backbone.num_frames):
        raise ValueError("config frame counts disagree")

    cap = cv2.VideoCapture(str(args.video))
    count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if count < expected: raise ValueError(f"video has {count} frames; checkpoint expects {expected}")
    indices = np.linspace(0, count - 1, expected, endpoint=True, dtype=np.int64)
    detector = get_model("resnet50_2020-07-20", max_size=2048, device=torch.device("cuda")); detector.eval()
    crops = []
    for index in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(index)); ok, bgr = cap.read()
        if not ok: raise ValueError(f"could not decode frame {index}")
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB); faces = detector.predict_jsons(rgb)
        faces = [face for face in faces if "bbox" in face]
        if not faces: raise ValueError(f"no face detected in frame {index}")
        face = max(faces, key=lambda item: ((item["bbox"][2]-item["bbox"][0]) *
            (item["bbox"][3]-item["bbox"][1]), item.get("score", 0)))
        x0, y0, x1, y1 = face["bbox"]; height, width = bgr.shape[:2]
        fw, fh = x1-x0, y1-y0
        x0, x1 = max(0, int(x0-.25*fw)), min(width, int(x1+.25*fw))
        y0, y1 = max(0, int(y0-.25*fh)), min(height, int(y1+.25*fh))
        crop = cv2.resize(bgr[y0:y1, x0:x1], (256, 256), interpolation=cv2.INTER_LINEAR)
        # Official test_vid removes a 15-pixel border from preprocessed crops.
        crops.append(Image.fromarray(cv2.cvtColor(crop[15:-15, 15:-15], cv2.COLOR_BGR2RGB)))
    cap.release()

    transform = final_transform(cfg.DATASET)
    frames = [transform(np.asarray(image.resize(tuple(map(int, cfg.DATASET.IMAGE_SIZE)))) / 255).float() for image in crops]
    tensor = torch.stack(frames).transpose(0, 1).unsqueeze(0).cuda(non_blocking=True)
    model = load_pretrained(build_model(cfg.MODEL, MODELS).float(), str(args.checkpoint)).cuda().eval()
    torch.cuda.reset_peak_memory_stats(); started = time.perf_counter()
    with torch.inference_mode(): outputs = model(tensor)
    torch.cuda.synchronize(); runtime_ms = (time.perf_counter() - started) * 1000
    raw = outputs[0]["temp_loc"].detach().float().cpu().reshape(-1)
    scores = raw.sigmoid(); score = float(scores[-1])
    print(json.dumps({"model_version": "FakeSTormer@official",
        "checkpoint": f"{args.checkpoint.name}#sha256={sha256(args.checkpoint)}",
        "model_score": score, "raw_output": raw.tolist(), "runtime_ms": runtime_ms,
        "peak_gpu_memory_mb": torch.cuda.max_memory_allocated() / 1024**2,
        "sample_scores": [{"timestamp": None, "score": float(value), "raw_output": [float(logit)]}
            for value, logit in zip(scores, raw)]}))


if __name__ == "__main__": main()
