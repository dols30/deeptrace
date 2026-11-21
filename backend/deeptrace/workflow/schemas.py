from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field
from deeptrace.schemas import ReviewCheck

Disposition = Literal["agree", "disagree", "uncertain", "needs_expert_review"]
AnalysisStatus = Literal[
    "UPLOADED", "PROCESSING", "AI_SCREENING_COMPLETE", "INVESTIGATOR_REVIEW",
    "EXPERT_REVIEW_REQUESTED", "SUPERVISOR_REVIEW", "CHANGES_REQUESTED", "FINALIZED",
]


class ReviewOut(BaseModel):
    id: str
    actor_id: str
    previous_value: Optional[str]
    new_value: str
    comment: str
    created_at: datetime


class AttributionOut(BaseModel):
    method: str
    available: bool
    summary: str
    metadata: dict = Field(default_factory=dict)


class FindingOut(BaseModel):
    id: str
    modality: Literal["audio", "video"]
    start_time: float
    end_time: Optional[float]
    model_name: str
    model_version: str
    preprocessing_version: str
    raw_logits: Optional[list[float]]
    raw_score: float
    normalized_score: Optional[float]
    calibrated_probability: Optional[float]
    threshold: float
    predicted_class: str
    attribution_method: Optional[str]
    score_scope: str
    human_disposition: Optional[str]
    attribution: Optional[AttributionOut]
    reviews: list[ReviewOut]


class ModelRunOut(BaseModel):
    id: str
    modality: str
    model_name: str
    model_version: str
    checkpoint: Optional[str]
    preprocessing_version: str
    status: str
    threshold: float
    raw_score: Optional[float]
    calibrated_probability: Optional[float]
    calibration_version: Optional[str]
    notes: list[str]
    development_mock: bool
    coverage: Optional[dict] = None
    coverage_limited: bool = False


class MediaOut(BaseModel):
    filename: str
    media_kind: Literal["audio", "video"]
    content_type: str
    size_bytes: int
    sha256: str
    duration_seconds: Optional[float]
    container: Optional[str]


class CommentOut(BaseModel):
    id: str
    author: str
    author_role: str
    body: str
    finding_id: Optional[str]
    parent_id: Optional[str]
    timestamp_seconds: Optional[float]
    mentions: list[str]
    resolved: bool
    created_at: datetime


class AnalysisSummary(BaseModel):
    id: str
    title: str
    status: str
    owner: str
    media_kind: str
    created_at: datetime
    finding_count: int
    legacy_report_id: Optional[str]


class AnalysisDetail(AnalysisSummary):
    media: MediaOut
    model_runs: list[ModelRunOut]
    findings: list[FindingOut]
    comments: list[CommentOut]
    limitation: str
    development_mock: bool
    review_checks: list[ReviewCheck] = Field(default_factory=list)


class DashboardOut(BaseModel):
    awaiting_my_review: list[AnalysisSummary]
    expert_review_requested: list[AnalysisSummary]
    reports_awaiting_approval: list[AnalysisSummary]
    recently_completed: list[AnalysisSummary]


class DispositionIn(BaseModel):
    disposition: Disposition
    comment: str = Field(default="", max_length=4000)


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    finding_id: Optional[str] = None
    parent_id: Optional[str] = None
    timestamp_seconds: Optional[float] = Field(default=None, ge=0)


class ReportSection(BaseModel):
    text: str = Field(default="", max_length=20000)
    origin: Literal["ai", "human"] = "human"


class ReportOut(BaseModel):
    id: str
    analysis_id: str
    status: str
    ai_original: dict[str, ReportSection]
    current: dict[str, ReportSection]
    revisions: list["RevisionOut"]


class RevisionOut(BaseModel):
    id: str
    author: str
    kind: str
    created_at: datetime


class ReportSave(BaseModel):
    sections: dict[str, ReportSection]


class RestoreIn(BaseModel):
    revision_id: str


class SectionDiff(BaseModel):
    section: str
    label: str
    ai_text: str
    current_text: str
    changed: bool
    current_origin: Literal["ai", "human"]


class AssistantTurn(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(max_length=4000)


class AssistantIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    history: list[AssistantTurn] = Field(default_factory=list, max_length=12)


class AssistantOut(BaseModel):
    answer: str
    citations: list[dict]
    advisory_only: bool = True
    provider: str = "rules"


class AuditOut(BaseModel):
    id: str
    actor_id: str
    action: str
    entity_type: str
    entity_id: str
    timestamp: datetime
    metadata: dict


class UserIn(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=8, max_length=256)
    role: Literal["investigator", "forensic_reviewer", "supervisor", "administrator"]
    display_name: str = Field(default="", max_length=80)


class UserOut(BaseModel):
    username: str
    display_name: str
    role: str
    active: bool


class RoleUpdate(BaseModel):
    role: Literal["investigator", "forensic_reviewer", "supervisor", "administrator"]


class SupplementaryMethodInfo(BaseModel):
    task: str
    model: str
    configured: bool
    kind: Literal['detector', 'interval_spotter']


class ModelInfo(BaseModel):
    video_model: str
    video_configured: bool
    scene_model: str = "community_forensics"
    scene_configured: bool = False
    audio_model: str
    audio_configured: bool
    decision_threshold: float
    face_decision_rule: str = "default_0_5"
    face_decision_threshold: float = 0.5
    calibration_version: Optional[str]
    preprocessing: dict[str, str]
    limitation: str
    note: str
    supplementary_methods: list[SupplementaryMethodInfo] = Field(default_factory=list)
