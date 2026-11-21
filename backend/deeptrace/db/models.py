"""Normalized workflow tables. Provenance is stored as new rows, not overwritten values."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Role(Base):
    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    description: Mapped[str] = mapped_column(Text, default="")


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    username: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(80), default="")
    password_hash: Mapped[str | None] = mapped_column(String(200), nullable=True)
    role_name: Mapped[str] = mapped_column(ForeignKey("roles.name"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    role: Mapped[Role] = relationship()
    analyses: Mapped[list["Analysis"]] = relationship(back_populates="owner")


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    legacy_report_id: Mapped[str | None] = mapped_column(String(36), unique=True, nullable=True)
    title: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(40), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    owner: Mapped[User] = relationship(back_populates="analyses")
    media_files: Mapped[list["MediaFile"]] = relationship(back_populates="analysis")
    model_runs: Mapped[list["ModelRun"]] = relationship(back_populates="analysis")
    findings: Mapped[list["Finding"]] = relationship(back_populates="analysis")
    comments: Mapped[list["Comment"]] = relationship(back_populates="analysis")
    report: Mapped["Report | None"] = relationship(back_populates="analysis", uselist=False)
    assignments: Mapped[list["ReviewAssignment"]] = relationship(back_populates="analysis")


class MediaFile(Base):
    __tablename__ = "media_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    media_kind: Mapped[str] = mapped_column(String(16))
    content_type: Mapped[str] = mapped_column(String(128))
    size_bytes: Mapped[int]
    sha256: Mapped[str] = mapped_column(String(64))
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    container: Mapped[str | None] = mapped_column(String(64), nullable=True)
    storage_key: Mapped[str] = mapped_column(Text)

    analysis: Mapped[Analysis] = relationship(back_populates="media_files")


class ModelRun(Base):
    __tablename__ = "model_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id"), index=True)
    modality: Mapped[str] = mapped_column(String(16))
    model_name: Mapped[str] = mapped_column(String(128))
    model_version: Mapped[str] = mapped_column(String(128))
    checkpoint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    preprocessing_version: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32))
    threshold: Mapped[float] = mapped_column(Float)
    raw_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    calibrated_probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    calibration_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sample_scores: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[list] = mapped_column(JSON, default=list)
    run_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    analysis: Mapped[Analysis] = relationship(back_populates="model_runs")
    findings: Mapped[list["Finding"]] = relationship(back_populates="model_run")


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id"), index=True)
    model_run_id: Mapped[str] = mapped_column(ForeignKey("model_runs.id"), index=True)
    modality: Mapped[str] = mapped_column(String(16))
    start_time: Mapped[float] = mapped_column(Float)
    end_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    model_name: Mapped[str] = mapped_column(String(128))
    model_version: Mapped[str] = mapped_column(String(128))
    preprocessing_version: Mapped[str] = mapped_column(String(128))
    raw_logits: Mapped[list | None] = mapped_column(JSON, nullable=True)
    raw_score: Mapped[float] = mapped_column(Float)
    normalized_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    calibrated_probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold: Mapped[float] = mapped_column(Float)
    predicted_class: Mapped[str] = mapped_column(String(64))
    attribution_method: Mapped[str | None] = mapped_column(String(64), nullable=True)
    score_scope: Mapped[str] = mapped_column(String(16), default="sample")
    human_disposition: Mapped[str | None] = mapped_column(String(32), nullable=True)

    analysis: Mapped[Analysis] = relationship(back_populates="findings")
    model_run: Mapped[ModelRun] = relationship(back_populates="findings")
    reviews: Mapped[list["FindingReview"]] = relationship(back_populates="finding")
    attribution: Mapped["AttributionArtifact | None"] = relationship(back_populates="finding", uselist=False)


class AttributionArtifact(Base):
    __tablename__ = "attribution_artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    finding_id: Mapped[str] = mapped_column(ForeignKey("findings.id"), unique=True)
    method: Mapped[str] = mapped_column(String(64))
    available: Mapped[bool] = mapped_column(Boolean, default=False)
    storage_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    artifact_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    finding: Mapped[Finding] = relationship(back_populates="attribution")


class FindingReview(Base):
    __tablename__ = "finding_reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    finding_id: Mapped[str] = mapped_column(ForeignKey("findings.id"), index=True)
    actor_id: Mapped[str] = mapped_column(String(128))
    previous_value: Mapped[str | None] = mapped_column(String(32), nullable=True)
    new_value: Mapped[str] = mapped_column(String(32))
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    finding: Mapped[Finding] = relationship(back_populates="reviews")


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id"), index=True)
    finding_id: Mapped[str | None] = mapped_column(ForeignKey("findings.id"), nullable=True)
    report_id: Mapped[str | None] = mapped_column(ForeignKey("reports.id"), nullable=True)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("comments.id"), nullable=True)
    author: Mapped[str] = mapped_column(String(128))
    author_role: Mapped[str] = mapped_column(String(64))
    body: Mapped[str] = mapped_column(Text)
    timestamp_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    mentions: Mapped[list] = mapped_column(JSON, default=list)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    analysis: Mapped[Analysis] = relationship(back_populates="comments")
    replies: Mapped[list["Comment"]] = relationship(back_populates="parent")
    parent: Mapped["Comment | None"] = relationship(back_populates="replies", remote_side="Comment.id")


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id"), unique=True)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    ai_original: Mapped[dict] = mapped_column(JSON)
    current_body: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    analysis: Mapped[Analysis] = relationship(back_populates="report")
    revisions: Mapped[list["ReportRevision"]] = relationship(back_populates="report")


class ReportRevision(Base):
    __tablename__ = "report_revisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id"), index=True)
    author: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(32))
    body: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    report: Mapped[Report] = relationship(back_populates="revisions")


class ReviewAssignment(Base):
    __tablename__ = "review_assignments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id"), index=True)
    assignee_username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    role_name: Mapped[str] = mapped_column(String(64))
    purpose: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    analysis: Mapped[Analysis] = relationship(back_populates="assignments")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    actor_id: Mapped[str] = mapped_column(String(128), index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    event_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
