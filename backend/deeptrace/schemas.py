from datetime import datetime, timezone
from uuid import uuid4

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


def operational_status(score: float | None, review: float | None, flag: float | None, *, validated: bool) -> str:
    """Map a score to UI status only when operational thresholds are validated."""
    if score is None:
        return "unavailable"
    if not validated or review is None or flag is None:
        return "threshold_not_validated"
    if not 0 <= review <= flag <= 1:
        raise ValueError("validated thresholds must satisfy 0 <= review <= flag <= 1")
    if score >= flag:
        return "red_flagged"
    if score >= review:
        return "yellow_review_recommended"
    return "green_not_flagged"


class MediaMetadata(BaseModel):
    filename: str
    media_kind: Literal["audio", "video"]
    content_type: str
    size_bytes: int
    sha256: str
    duration_seconds: Optional[float] = None
    container: Optional[str] = None
    codecs: List[str] = Field(default_factory=list)
    extraction_warnings: List[str] = Field(default_factory=list)


class Anomaly(BaseModel):
    component: Literal["audio", "video", "media"]
    code: str
    description: str
    severity: Literal["info", "low", "medium", "high"]


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)


RoleName = Literal["analyst", "investigator", "forensic_reviewer", "supervisor", "administrator"]


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    role: RoleName


class ProfileUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=80)


class ProfileResponse(ProfileUpdate):
    username: str
    role: RoleName


class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class CommentResponse(CommentCreate):
    comment_id: int
    report_id: str
    author: str
    author_role: RoleName
    created_at: datetime


class NotebookUpdate(BaseModel):
    body: str = Field(default="", max_length=10000)


class NotebookResponse(NotebookUpdate):
    report_id: str
    author: str
    updated_at: datetime


class ModelSample(BaseModel):
    """One model output. raw_score is not a calibrated probability."""

    start_time: float
    end_time: Optional[float] = None
    raw_score: float = Field(ge=0, le=1)
    raw_logits: Optional[List[float]] = None
    predicted_class: Literal["possible_manipulation", "no_elevated_signal"]
    score_scope: Literal["sample", "file", "aggregate"] = "sample"


class ComponentResult(BaseModel):
    component: Literal["audio", "video"]
    status: Literal["functional", "stub", "not_applicable", "unavailable", "error"]
    model_name: str
    model_version: str
    checkpoint: Optional[str] = None
    synthetic_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    anomalies: List[Anomaly] = Field(default_factory=list)
    timestamps_seconds: List[float] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)
    samples: List[ModelSample] = Field(default_factory=list)
    attribution: Optional[dict] = None
    coverage: Optional[dict] = None
    # Explicit detector semantics. ``synthetic_confidence`` remains readable
    # for backwards compatibility with persisted v0.2 reports.
    detector_id: Optional[str] = None
    detector_name: Optional[str] = None
    task: Optional[Literal["face_manipulation", "synthetic_video", "audio_spoof"]] = None
    raw_score: Optional[float] = Field(default=None, ge=0, le=1)
    display_score: Optional[float] = Field(default=None, ge=0, le=1)
    calibrated_probability: Optional[float] = Field(default=None, ge=0, le=1)
    threshold: Optional[float] = Field(default=None, ge=0, le=1)
    threshold_source: Optional[str] = None
    threshold_validated: bool = False
    detector_status: Literal["score_only", "not_available", "error"] = "not_available"
    aggregation_method: Optional[str] = None
    num_samples: int = Field(default=0, ge=0)
    limitations: List[str] = Field(default_factory=list)
    thresholds: dict[str, Optional[float]] = Field(default_factory=lambda: {"review": None, "flag": None})
    threshold_validation: dict = Field(default_factory=lambda: {
        "validated": False, "dataset": None, "target_fpr": None,
    })
    operational_status: str = "threshold_not_validated"

    @model_validator(mode="after")
    def populate_score_aliases(self):
        score = self.raw_score if self.raw_score is not None else self.synthetic_confidence
        if self.raw_score is None:
            self.raw_score = score
        if self.display_score is None:
            self.display_score = score
        if self.detector_name is None:
            self.detector_name = self.model_name
        if not self.num_samples:
            self.num_samples = len(self.samples)
        if self.status == "functional" and score is not None and self.detector_status == "not_available":
            self.detector_status = "score_only"
        elif self.status == "error":
            self.detector_status = "error"
        validated = bool(self.threshold_validation.get("validated", self.threshold_validated))
        self.threshold_validated = validated
        self.operational_status = operational_status(
            score, self.thresholds.get("review"), self.thresholds.get("flag"), validated=validated,
        )
        return self


class ReviewCheck(BaseModel):
    """Supplementary measurements, deliberately separate from detector decisions."""

    technique: str
    title: str
    modality: Literal["audio", "video"]
    status: Literal["measured", "unavailable", "error", "not_applicable"]
    method: str
    summary: str
    measurements: dict[str, float | int | str] = Field(default_factory=dict)
    intervals: List[dict] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    version: str = "review-signals-v1"
    validated: bool = False


class AdvisoryReport(BaseModel):
    report_version: str = "0.3"
    report_id: str = Field(default_factory=lambda: str(uuid4()))
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    examination_scope: str = "Automated screening for synthetic-media indicators in the submitted file."
    integrity: dict[str, str] = Field(default_factory=dict)
    methods: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    references: List[dict[str, str]] = Field(default_factory=list)
    review_status: str = "Pending qualified human review"
    advisory_only: bool = True
    disclaimer: str
    media: MediaMetadata
    overall_synthetic_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    evidence_summary: List[dict] = Field(default_factory=list)
    summary: str
    anomalies: List[Anomaly]
    components: List[ComponentResult]
    recommended_action: str
    owner: Optional[str] = None
    reviewer: Optional[str] = None
    workflow_status: Literal["draft", "submitted", "in_review", "reviewed"] = "draft"
    analysis_id: Optional[str] = None
    review_checks: List[ReviewCheck] = Field(default_factory=list)
    processing: dict = Field(default_factory=dict)
