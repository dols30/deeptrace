from __future__ import annotations

import json, shlex, subprocess, time
from pathlib import Path

from .models import ExperimentalDetectorResult, ExperimentalSample


def run_json_detector(command: str, video: Path, *, timeout: int = 1800) -> tuple[dict, float]:
    if not video.is_file():
        raise FileNotFoundError(video)
    args = [part.format(video_path=str(video)) for part in shlex.split(command)]
    started = time.perf_counter()
    completed = subprocess.run(args, capture_output=True, text=True, check=True, timeout=timeout)
    runtime_ms = (time.perf_counter() - started) * 1000
    payload = json.loads(completed.stdout)
    return payload, runtime_ms


def result_from_payload(payload: dict, runtime_ms: float, *, detector_id: str, detector_name: str,
                        task: str, aggregation: str, limitations: list[str]) -> ExperimentalDetectorResult:
    score = float(payload["model_score"])
    if not 0 <= score <= 1:
        raise ValueError("experimental detector score outside [0,1]")
    samples = [ExperimentalSample(**item) for item in payload.get("sample_scores", [])]
    return ExperimentalDetectorResult(detector_id=detector_id, detector_name=detector_name, task=task,
        raw_score=score, model_score=score, calibrated_probability=None, threshold=None,
        threshold_source=None, threshold_validated=False, status="score_only",
        aggregation_method=aggregation, sample_scores=samples,
        model_version=str(payload.get("model_version", "unreported")), checkpoint=payload.get("checkpoint"),
        runtime_ms=float(payload.get("runtime_ms", runtime_ms)),
        peak_gpu_memory_mb=payload.get("peak_gpu_memory_mb"), limitations=limitations)
