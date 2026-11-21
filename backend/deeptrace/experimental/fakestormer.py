from __future__ import annotations

import json, subprocess
from pathlib import Path

from .command import result_from_payload, run_json_detector
from .models import ExperimentalDetectorResult


class FakeSTormerAdapter:
    """Subprocess adapter for the official FakeSTormer environment.

    The command must contain ``{video_path}`` and emit the documented JSON
    contract. It is deliberately not referenced by ``deeptrace.api``.
    """
    detector_id = "fakestormer"
    detector_name = "FakeSTormer"
    task = "face_manipulation"

    def __init__(self, command: str | None, checkpoint: Path | None = None):
        self.command, self.checkpoint = command, checkpoint

    def predict_video(self, path: Path) -> ExperimentalDetectorResult:
        if not self.command:
            return self._blocked("FakeSTormer command is not configured")
        if self.checkpoint is not None and not self.checkpoint.is_file():
            return self._blocked(f"FakeSTormer checkpoint is missing: {self.checkpoint}")
        try:
            payload, runtime = run_json_detector(self.command, path)
            return result_from_payload(payload, runtime, detector_id=self.detector_id,
                detector_name=self.detector_name, task=self.task,
                aggregation="official_four_frame_temporal_output",
                limitations=["EXPERIMENTAL — NOT USED FOR FINAL DEEPTRACE ASSESSMENT.",
                    "Official single-video inference uses four face crops and the final sigmoid temporal-location output.",
                    "The SnT academic license restricts use to academic research, development, testing, and validation."])
        except (OSError, ValueError, KeyError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
            return self._blocked(f"{type(exc).__name__}: {exc}")

    def _blocked(self, reason: str) -> ExperimentalDetectorResult:
        return ExperimentalDetectorResult(detector_id=self.detector_id, detector_name=self.detector_name,
            task=self.task, status="blocked", model_version="official-adapter-unavailable",
            checkpoint=str(self.checkpoint) if self.checkpoint else None, error=reason,
            limitations=["EXPERIMENTAL — NOT USED FOR FINAL DEEPTRACE ASSESSMENT."])
