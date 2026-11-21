from __future__ import annotations

from pydantic import BaseModel, Field


class ExperimentalSample(BaseModel):
    timestamp: float | None = None
    score: float = Field(ge=0, le=1)
    raw_output: list[float] | None = None


class ExperimentalDetectorResult(BaseModel):
    detector_id: str
    detector_name: str
    task: str
    raw_score: float | None = Field(default=None, ge=0, le=1)
    model_score: float | None = Field(default=None, ge=0, le=1)
    calibrated_probability: float | None = Field(default=None, ge=0, le=1)
    threshold: float | None = Field(default=None, ge=0, le=1)
    threshold_source: str | None = None
    threshold_validated: bool = False
    status: str
    aggregation_method: str | None = None
    sample_scores: list[ExperimentalSample] = Field(default_factory=list)
    model_version: str
    checkpoint: str | None = None
    runtime_ms: float = Field(default=0, ge=0)
    peak_gpu_memory_mb: float | None = Field(default=None, ge=0)
    experimental: bool = True
    limitations: list[str] = Field(default_factory=list)
    error: str | None = None
