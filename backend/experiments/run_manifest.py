#!/usr/bin/env python3
"""Run a pinned DeepTrace adapter over a labeled manifest on a compute cluster."""

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_file(value: str, name: str) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise SystemExit(f"{name} is not a file: {path}")
    return path


def command_output(command: list[str]) -> tuple[dict, float]:
    started = time.perf_counter()
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    elapsed = time.perf_counter() - started
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"command failed ({result.returncode}): {detail}")
    try:
        return json.loads(result.stdout), elapsed
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"adapter returned invalid JSON: {result.stdout[:500]}") from exc


def sample_frames(media: Path, directory: Path, interval: float, maximum: int) -> float:
    started = time.perf_counter()
    command = [
        "ffmpeg", "-nostdin", "-v", "error", "-i", str(media),
        "-vf", f"fps=1/{interval}", "-frames:v", str(maximum),
        str(directory / "frame_%06d.jpg"),
    ]
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(f"ffmpeg failed: {result.stderr.strip()}")
    return time.perf_counter() - started


def read_manifest(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows or not {"id", "path", "label"}.issubset(rows[0]):
        raise SystemExit("Dataset CSV needs id,path,label and at least one row")
    for row in rows:
        if row["label"] not in {"0", "1"}:
            raise SystemExit(f"Label for {row['id']} must be 0 or 1")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("modality", choices=["audio", "video"])
    parser.add_argument("dataset", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cuda")
    parser.add_argument("--aasist-python", default="")
    parser.add_argument("--aasist-weights", default="")
    parser.add_argument("--aasist-variant", choices=["aasist", "aasist-l"], default="aasist")
    parser.add_argument("--efficientnet-python", default="")
    parser.add_argument("--efficientnet-weights", default="")
    parser.add_argument("--landmarks", default="")
    parser.add_argument("--frame-interval", type=float, default=1.0)
    parser.add_argument("--max-frames", type=int, default=120)
    args = parser.parse_args()

    repo = args.repo_root.resolve()
    rows = read_manifest(args.dataset.resolve())
    args.output_dir.mkdir(parents=True, exist_ok=True)
    scores_path = args.output_dir / "scores.csv"
    records_path = args.output_dir / "records.jsonl"

    if args.modality == "audio":
        python = require_file(args.aasist_python, "AASIST_PYTHON")
        weights = require_file(args.aasist_weights, "AASIST_WEIGHTS")
        upstream = repo / "vendor/aasist"
        adapter = repo / "scripts/inference/aasist.py"
        asset_hashes = {"aasist_weights": sha256(weights)}
    else:
        python = require_file(args.efficientnet_python, "EFFICIENTNET_PYTHON")
        weights = require_file(args.efficientnet_weights, "EFFICIENTNET_WEIGHTS")
        landmarks = require_file(args.landmarks, "LANDMARKS_WEIGHTS")
        upstream = repo / "vendor/DeepfakeBench"
        adapter = repo / "scripts/inference/efficientnetb4.py"
        asset_hashes = {"efficientnet_weights": sha256(weights), "landmarks": sha256(landmarks)}
    if not upstream.is_dir():
        raise SystemExit(f"Pinned upstream source is missing: {upstream}; run scripts/download_models.sh")

    metadata = {
        "modality": args.modality,
        "device": args.device,
        "hostname": os.uname().nodename,
        "dataset": str(args.dataset.resolve()),
        "dataset_sha256": sha256(args.dataset.resolve()),
        "asset_sha256": asset_hashes,
        "frame_interval": args.frame_interval if args.modality == "video" else None,
        "max_frames": args.max_frames if args.modality == "video" else None,
    }
    (args.output_dir / "run.json").write_text(json.dumps(metadata, indent=2) + "\n")

    with scores_path.open("w", newline="") as scores, records_path.open("w") as records:
        writer = csv.DictWriter(scores, fieldnames=["id", "label", "score"])
        writer.writeheader()
        for index, row in enumerate(rows, 1):
            media = Path(row["path"]).expanduser().resolve()
            record = {"id": row["id"], "label": int(row["label"]), "path": str(media)}
            try:
                if not media.is_file():
                    raise RuntimeError(f"media file not found: {media}")
                preprocessing_seconds = 0.0
                if args.modality == "audio":
                    command = [str(python), str(adapter), "--repo", str(upstream),
                               "--weights", str(weights), "--audio", str(media),
                               "--variant", args.aasist_variant, "--device", args.device]
                    payload, inference_seconds = command_output(command)
                    score = float(payload["fake_probability"])
                else:
                    with tempfile.TemporaryDirectory(prefix="deeptrace-eval-") as temp:
                        frames = Path(temp)
                        preprocessing_seconds = sample_frames(
                            media, frames, args.frame_interval, args.max_frames
                        )
                        command = [str(python), str(adapter), "--repo", str(upstream),
                                   "--weights", str(weights), "--landmarks", str(landmarks),
                                   "--frames", str(frames), "--device", args.device]
                        payload, inference_seconds = command_output(command)
                    samples = payload["samples"]
                    if not samples:
                        raise RuntimeError("no alignable faces were scored")
                    score = sum(float(item["fake_probability"]) for item in samples) / len(samples)
                record.update({"status": "ok", "score": score,
                               "preprocessing_seconds": preprocessing_seconds,
                               "inference_seconds": inference_seconds, "adapter_output": payload})
                writer.writerow({"id": row["id"], "label": row["label"], "score": score})
                scores.flush()
            except Exception as exc:  # Preserve failures for coverage analysis and continue the run.
                record.update({"status": "error", "error": str(exc)})
            records.write(json.dumps(record, sort_keys=True) + "\n")
            records.flush()
            print(f"[{index}/{len(rows)}] {row['id']}: {record['status']}", flush=True)

    if scores_path.stat().st_size:
        metrics = subprocess.run(
            [shutil.which("python3") or "python3", str(repo / "scripts/benchmark.py"), str(scores_path)],
            text=True, capture_output=True, check=False,
        )
        if metrics.returncode == 0:
            (args.output_dir / "metrics.json").write_text(metrics.stdout)
    print(f"Results written to {args.output_dir}")


if __name__ == "__main__":
    main()
