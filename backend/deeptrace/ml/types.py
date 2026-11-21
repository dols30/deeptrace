"""Detector contracts. Scores stay separate from calibrated probabilities."""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class FindingDraft:
    modality: str
    start_time: float
    end_time: float | None
    raw_logits: list[float] | None
    raw_score: float
    normalized_score: float | None
    calibrated_probability: float | None
    threshold: float
    predicted_class: str
    score_scope: str
    attribution_method: str | None
    attribution: dict = field(default_factory=dict)


@dataclass
class DetectionResult:
    model_name: str
    model_version: str
    checkpoint: str | None
    modality: str
    status: str
    raw_logits: list[float] | None
    score: float | None
    calibrated_probability: float | None
    calibration_version: str | None
    predicted_class: str | None
    threshold: float
    preprocessing_version: str
    findings: list[FindingDraft]
    sample_scores: list[dict]
    notes: list[str]
    metadata: dict = field(default_factory=dict)


class VideoDetector(Protocol):
    def analyze(self, frames_dir, metadata) -> DetectionResult: ...

    def explain(self, detection: DetectionResult) -> dict: ...


class AudioDetector(Protocol):
    def analyze(self, audio_path, metadata) -> DetectionResult: ...

    def explain(self, detection: DetectionResult) -> dict: ...
