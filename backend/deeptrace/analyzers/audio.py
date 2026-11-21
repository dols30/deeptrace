from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path

from deeptrace.analyzers.base import MediaAnalyzer, command_args
from deeptrace.schemas import Anomaly, ComponentResult, MediaMetadata, ModelSample


class AudioCommandAnalyzer(MediaAnalyzer):
    """Shared audio subprocess protocol and result interpretation."""

    model_name: str
    command_setting: str
    detector_id = "audio_spoof_detector"
    task = "audio_spoof"

    def __init__(self, command: str | None):
        self.command = command
        self.last_profile = None

    def _command(self, path: Path) -> list[str]:
        return command_args(self.command, audio_path=path)

    def analyze(self, path: Path, metadata: MediaMetadata) -> ComponentResult:
        self.last_profile = None
        if not self.command:
            return ComponentResult(component="audio", status="unavailable", model_name=self.model_name,
                model_version="unconfigured", detector_id=self.detector_id, task=self.task,
                notes=[f"Set {self.command_setting} after installing reviewed code and weights."])
        try:
            result = subprocess.run(self._command(path), capture_output=True,
                text=True, timeout=900, check=True)
            payload = json.loads(result.stdout)
            self.last_profile = payload
            score = float(payload["fake_probability"])
            if not 0 <= score <= 1:
                raise ValueError("score outside [0,1]")
            samples = []
            for item in payload.get("samples", []):
                start, end = float(item["start_time"]), float(item["end_time"])
                if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
                    raise ValueError("Invalid audio window")
                if samples and start < samples[-1].end_time:
                    raise ValueError("Overlapping or unordered audio windows")
                samples.append(ModelSample(start_time=start, end_time=end, raw_score=float(item["fake_probability"]),
                    raw_logits=item.get("logits"), predicted_class="possible_manipulation" if float(item["fake_probability"]) >= .5 else "no_elevated_signal"))
            coverage = payload.get("coverage")
            if coverage is not None:
                if not samples or coverage.get("mode") not in {"first", "full"} or not isinstance(coverage.get("complete"), bool):
                    raise ValueError("Coverage requires window-level evidence")
                duration = float(coverage["duration_seconds"])
                if not math.isfinite(duration) or duration <= 0 or coverage.get("windows") != len(samples):
                    raise ValueError("Invalid decoded audio coverage")
                analyzed = sum(item.end_time - item.start_time for item in samples)
                if not math.isclose(float(coverage["analyzed_seconds"]), analyzed, abs_tol=.001):
                    raise ValueError("Coverage does not match audio samples")
                if coverage.get("complete") and not math.isclose(analyzed, float(coverage["duration_seconds"]), abs_tol=.001):
                    raise ValueError("Complete coverage does not match decoded duration")
                if samples[0].start_time != 0 or samples[-1].end_time > duration + .001:
                    raise ValueError("Windows outside decoded audio")
                if any(not math.isclose(a.end_time, b.start_time, abs_tol=.001) for a,b in zip(samples,samples[1:])):
                    raise ValueError("Gaps in declared analyzed coverage")
                if coverage["mode"] == "full" and not math.isclose(score, sum(s.raw_score for s in samples)/len(samples), abs_tol=.000001):
                    raise ValueError("Window mean does not match declared full-mode score")
            flagged = [item.start_time for item in samples if item.raw_score >= .5]
            anomalies = ([Anomaly(component="audio", code="ELEVATED_SPOOF_SCORE",
                description="One or more audio windows exceeded the provisional review threshold." if samples else "The file-level audio spoof score exceeded the provisional review threshold.", severity="medium")]
                if flagged or score >= 0.5 else [])
            logits = payload.get("logits")
            raw_attribution = payload.get("attribution")
            attribution = {}
            if isinstance(raw_attribution, dict) and raw_attribution.get("windows"):
                attribution = raw_attribution
            for key in ("temporal_relevance", "spectral_relevance", "graph_attention"):
                if key in payload:
                    attribution[key] = payload[key]
            return ComponentResult(component="audio", status="functional", model_name=self.model_name,
                model_version=payload.get("model_version", "unpinned"), checkpoint=payload.get("checkpoint"),
                synthetic_confidence=score, anomalies=anomalies,
                samples=samples or [ModelSample(start_time=0.0, end_time=metadata.duration_seconds, raw_score=score,
                    raw_logits=logits if isinstance(logits, list) else None,
                    predicted_class="possible_manipulation" if score >= 0.5 else "no_elevated_signal",
                    score_scope="file")],
                attribution=attribution or None,
                coverage=coverage, timestamps_seconds=flagged,
                detector_id=self.detector_id, task=self.task, raw_score=score,
                calibrated_probability=None, threshold=0.5,
                threshold_source="default_model_decision_rule", threshold_validated=False,
                aggregation_method=payload.get("aggregation_method", "file_level_model_output"),
                limitations=["The score is uncalibrated and is not a probability of spoofed speech."],
                notes=["Window timestamps describe the actual analyzed samples; coverage excludes repeated padding." if samples else "The baseline produces a file-level score; segment timestamps are available only when the adapter returns them.",
                    "Scores are uncalibrated model outputs; the transform is recorded in the runner notes.",
                    *payload.get("notes", [])])
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError, KeyError, ValueError, TypeError, AttributeError, IndexError) as exc:
            detail = getattr(exc, "stderr", None)
            diagnostic = f" Diagnostic: {detail.strip()[-1000:]}" if isinstance(detail, str) and detail.strip() else ""
            return ComponentResult(component="audio", status="error", model_name=self.model_name, model_version="unknown",
                detector_id=self.detector_id, task=self.task,
                notes=[f"{self.model_name} adapter failed closed: {type(exc).__name__}.{diagnostic}"])


class AASISTAudioAnalyzer(AudioCommandAnalyzer):
    model_name = "AASIST"
    command_setting = "DEEPTRACE_AASIST_COMMAND"
    detector_id = "aasist"

    def __init__(self, command: str | None, variant: str = "aasist", window_mode: str = "first"):
        super().__init__(command)
        if window_mode not in {"first", "full"}:
            raise ValueError("Unknown AASIST window policy")
        self.window_mode = window_mode
        self.model_name = "AASIST-L" if variant == "aasist-l" else "AASIST"

    def _command(self, path: Path) -> list[str]:
        command = super()._command(path)
        return [*command, "--window-mode", "full"] if self.window_mode == "full" else command


class Nes2NetAudioAnalyzer(AudioCommandAnalyzer):
    """Nes2Net speech adapter."""
    model_name = 'Nes2Net'
    command_setting = "DEEPTRACE_NES2NET_COMMAND"
