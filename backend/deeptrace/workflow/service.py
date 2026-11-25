"""Case workflow. AI text is preserved; investigator text is a new revision."""

import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.orm import Session, selectinload

from deeptrace.config import settings
from deeptrace.db.models import (
    Analysis, AttributionArtifact, AuditEvent, Comment, Finding, FindingReview, MediaFile,
    MediaObservation, ModelRun, Report, ReportRevision, ReviewAssignment, User,
)
from deeptrace.db.session import ROLES
from deeptrace.ml.assistant import RulesCaseAssistant
from deeptrace.ml.attribution import AASISTAudioAttribution
from deeptrace.ml.detectors import detection_from_component
from deeptrace.ml.decision_rules import EFFICIENTNET_RULES
from deeptrace.schemas import AdvisoryReport
from deeptrace.workflow.access import (
    DISPOSITIONS, EDITABLE_STATUSES, WorkflowError, can_read, can_review_finding, canonical_role,
    display_user, hash_password, mentions_in,
)

logger = logging.getLogger("deeptrace.workflow")
assistant = RulesCaseAssistant()

LIMITATION = (
    "DeepTrace provides automated screening assistance. Model outputs and "
    "attribution visualizations are advisory and require qualified human interpretation."
)

SECTIONS = [
    ("analysis_information", "Analysis Information"),
    ("media_information", "Media Information"),
    ("models_used", "Models Used"),
    ("automated_screening_results", "Automated Screening Results"),
    ("audio_findings", "Audio Findings"),
    ("video_findings", "Video Findings"),
    ("investigator_assessment", "Investigator Assessment"),
    ("items_requiring_additional_review", "Items Requiring Additional Review"),
    ("limitations", "Limitations"),
    ("reviewer_notes", "Reviewer Notes"),
]
SECTION_KEYS = [key for key, _label in SECTIONS]
SECTION_LABELS = dict(SECTIONS)
HUMAN_SECTIONS = {"investigator_assessment", "items_requiring_additional_review", "reviewer_notes"}


def record_screening(session: Session, *, owner: str, role: str, report: AdvisoryReport, media_path: str) -> str:
    user = _ensure_user(session, owner, role)
    now = datetime.now(timezone.utc)
    analysis = Analysis(
        id=str(uuid4()), owner_id=user.id, legacy_report_id=report.report_id,
        title=report.media.filename, status="AI_SCREENING_COMPLETE", created_at=now, updated_at=now,
    )
    session.add(analysis)
    session.add(MediaFile(
        id=str(uuid4()), analysis_id=analysis.id, filename=report.media.filename,
        media_kind=report.media.media_kind, content_type=report.media.content_type,
        size_bytes=report.media.size_bytes, sha256=report.media.sha256,
        duration_seconds=report.media.duration_seconds, container=report.media.container,
        storage_key=media_path,
    ))
    _audit(session, owner, "MEDIA_UPLOADED", "analysis", analysis.id, {})
    _audit(session, owner, "ANALYSIS_STARTED", "analysis", analysis.id, {})
    created: list[Finding] = []
    recorded_modalities = set()
    for component in report.components:
        preprocessing = _preprocessing(component.component)
        if component.detector_id == 'cnn_gan_artifacts':
            preprocessing += '-rgb-imagenet-uncropped-v1'
        elif component.detector_id == 'lfcc_lcnn_artifacts':
            preprocessing += '-lfcc20-deltas-fft1024-v1'
        if component.coverage and component.coverage.get("mode") == "full":
            preprocessing += "-full-window-v1"
        detection = detection_from_component(
            component, report.media,
            threshold=None if component.detector_id == "deepfakebench_efficientnet_b4" else settings.decision_threshold,
            preprocessing_version=preprocessing,
        )
        if component.component not in recorded_modalities:
            detection.metadata["review_checks"] = [item.model_dump(mode="json") for item in report.review_checks if item.modality == component.component]
            recorded_modalities.add(component.component)
        model_run = ModelRun(
            id=str(uuid4()), analysis_id=analysis.id, modality=component.component,
            model_name=detection.model_name, model_version=detection.model_version,
            checkpoint=detection.checkpoint, preprocessing_version=detection.preprocessing_version,
            status=detection.status, threshold=detection.threshold, raw_score=detection.score,
            calibrated_probability=None, calibration_version=None,
            sample_scores=detection.sample_scores, notes=detection.notes,
            run_metadata=detection.metadata, created_at=now,
        )
        session.add(model_run)
        session.flush()
        for draft in detection.findings:
            finding = Finding(
                id=str(uuid4()), analysis_id=analysis.id, model_run_id=model_run.id,
                modality=draft.modality, start_time=draft.start_time, end_time=draft.end_time,
                model_name=detection.model_name, model_version=detection.model_version,
                preprocessing_version=detection.preprocessing_version, raw_logits=draft.raw_logits,
                raw_score=draft.raw_score, normalized_score=draft.normalized_score,
                calibrated_probability=None, threshold=draft.threshold,
                predicted_class=draft.predicted_class, attribution_method=draft.attribution_method,
                score_scope=draft.score_scope, human_disposition=None,
            )
            session.add(finding)
            session.flush()
            explanation = _explain(draft.modality, draft.attribution)
            session.add(AttributionArtifact(
                id=str(uuid4()), finding_id=finding.id, method=explanation["method"],
                available=bool(explanation.get("available")), summary=explanation["summary"],
                artifact_metadata={key: value for key, value in explanation.items() if key != "summary"},
                created_at=now,
            ))
            created.append(finding)
    body = _draft_report(report, created)
    report_row = Report(
        id=str(uuid4()), analysis_id=analysis.id, status="draft",
        ai_original=body, current_body=body, created_at=now, updated_at=now,
    )
    session.add(report_row)
    session.flush()
    session.add(ReportRevision(
        id=str(uuid4()), report_id=report_row.id, author="deeptrace", kind="ai_generated", body=body, created_at=now,
    ))
    _audit(session, owner, "ANALYSIS_COMPLETED", "analysis", analysis.id, {"finding_count": len(created)})
    _audit(session, owner, "REPORT_GENERATED", "report", report_row.id, {"analysis_id": analysis.id})
    logger.info("analysis_completed %s", json.dumps({"analysis_id": analysis.id, "actor_id": owner}))
    return analysis.id


def dashboard(session: Session, user: dict) -> dict:
    role = canonical_role(str(user["role"]))
    owner = user["sub"]
    if role == "forensic_reviewer":
        awaiting = _summaries(session, user, statuses=["EXPERT_REVIEW_REQUESTED"])
    elif role == "supervisor":
        awaiting = _summaries(session, user, statuses=["SUPERVISOR_REVIEW"])
    elif role == "administrator":
        awaiting = []
    else:
        awaiting = _summaries(session, user, statuses=["AI_SCREENING_COMPLETE", "INVESTIGATOR_REVIEW", "CHANGES_REQUESTED"], owner=owner)
    expert = _summaries(session, user, statuses=["EXPERT_REVIEW_REQUESTED"], owner=owner if role == "investigator" else None)
    approval = _summaries(session, user, statuses=["SUPERVISOR_REVIEW"]) if role in {"supervisor", "administrator"} else []
    completed = _summaries(session, user, statuses=["FINALIZED"], owner=owner if role == "investigator" else None)
    return {
        "awaiting_my_review": awaiting[:8],
        "expert_review_requested": expert[:8],
        "reports_awaiting_approval": approval[:8],
        "recently_completed": completed[:8],
    }


def queue(session: Session, user: dict) -> list[dict]:
    role = canonical_role(str(user["role"]))
    if role == "forensic_reviewer":
        statuses = ["EXPERT_REVIEW_REQUESTED"]
        owner = None
    elif role == "supervisor":
        statuses = ["SUPERVISOR_REVIEW", "CHANGES_REQUESTED"]
        owner = None
    elif role == "administrator":
        statuses = ["EXPERT_REVIEW_REQUESTED", "SUPERVISOR_REVIEW", "CHANGES_REQUESTED"]
        owner = None
    else:
        statuses = ["AI_SCREENING_COMPLETE", "INVESTIGATOR_REVIEW", "EXPERT_REVIEW_REQUESTED", "CHANGES_REQUESTED"]
        owner = user["sub"]
    return _summaries(session, user, statuses=statuses, owner=owner)


def search(session: Session, user: dict, query: str) -> list[dict]:
    needle = f"%{query.strip().lower()}%"
    if needle == "%%":
        raise WorkflowError(422, "Enter a search term")
    visible = _visible_ids(session, user)
    if not visible:
        return []
    filename_ids = set(session.scalars(
        select(MediaFile.analysis_id).where(
            MediaFile.analysis_id.in_(visible), func.lower(MediaFile.filename).like(needle),
        )
    ))
    comment_ids = set(session.scalars(
        select(Comment.analysis_id).where(
            Comment.analysis_id.in_(visible), func.lower(Comment.body).like(needle),
        )
    ))
    title_ids = set(session.scalars(
        select(Analysis.id).where(Analysis.id.in_(visible), func.lower(Analysis.title).like(needle))
    ))
    matched = filename_ids | comment_ids | title_ids
    if not matched:
        return []
    return [_summary(item) for item in _load_many(session, matched)]


def get_analysis(session: Session, user: dict, analysis_id: str) -> dict:
    analysis = _require(session, user, analysis_id)
    return _detail(analysis)


def media_path(session: Session, user: dict, analysis_id: str) -> str:
    analysis = _require(session, user, analysis_id)
    if not analysis.media_files:
        raise WorkflowError(404, "Media not found")
    return analysis.media_files[0].storage_key


def review_finding(session: Session, user: dict, analysis_id: str, finding_id: str, disposition: str, comment: str) -> dict:
    if disposition not in DISPOSITIONS:
        raise WorkflowError(422, "Unknown disposition")
    analysis = _require(session, user, analysis_id)
    if analysis.status == "FINALIZED":
        raise WorkflowError(409, "This analysis is finalized")
    if not can_review_finding(user, analysis):
        raise WorkflowError(403, "You cannot review findings on this analysis")
    finding = next((item for item in analysis.findings if item.id == finding_id), None)
    if finding is None:
        raise WorkflowError(404, "Finding not found")
    previous = finding.human_disposition
    review = FindingReview(
        id=str(uuid4()), finding_id=finding.id, actor_id=str(user["sub"]),
        previous_value=previous, new_value=disposition, comment=comment.strip(),
        created_at=datetime.now(timezone.utc),
    )
    finding.human_disposition = disposition
    finding.reviews.append(review)
    if disposition == "needs_expert_review" and analysis.status in EDITABLE_STATUSES | {"INVESTIGATOR_REVIEW"}:
        analysis.status = "EXPERT_REVIEW_REQUESTED"
        session.add(ReviewAssignment(
            id=str(uuid4()), analysis_id=analysis.id, assignee_username=None,
            role_name="forensic_reviewer", purpose="expert_review", created_at=datetime.now(timezone.utc),
        ))
    elif analysis.status == "AI_SCREENING_COMPLETE":
        analysis.status = "INVESTIGATOR_REVIEW"
    _audit(session, str(user["sub"]), "FINDING_REVIEWED", "finding", finding.id, {
        "previous_value": previous, "new_value": disposition, "analysis_id": analysis.id,
    })
    session.flush()
    return _finding_out(finding)


def add_comment(session: Session, user: dict, analysis_id: str, body: str, finding_id: str | None, parent_id: str | None, timestamp_seconds: float | None) -> dict:
    analysis = _require(session, user, analysis_id)
    text = body.strip()
    if not text:
        raise WorkflowError(422, "Comment cannot be empty")
    if finding_id and finding_id not in {item.id for item in analysis.findings}:
        raise WorkflowError(404, "Finding not found")
    if parent_id and parent_id not in {item.id for item in analysis.comments}:
        raise WorkflowError(404, "Comment not found")
    comment = Comment(
        id=str(uuid4()), analysis_id=analysis.id, finding_id=finding_id, parent_id=parent_id,
        author=str(user["sub"]), author_role=canonical_role(str(user["role"])), body=text,
        timestamp_seconds=timestamp_seconds, mentions=mentions_in(text), resolved=False,
        created_at=datetime.now(timezone.utc),
    )
    session.add(comment)
    if analysis.status == "AI_SCREENING_COMPLETE" and canonical_role(str(user["role"])) == "investigator":
        analysis.status = "INVESTIGATOR_REVIEW"
    _audit(session, str(user["sub"]), "COMMENT_CREATED", "comment", comment.id, {"analysis_id": analysis.id})
    return _comment_out(comment)


def resolve_comment(session: Session, user: dict, analysis_id: str, comment_id: str, resolved: bool) -> dict:
    analysis = _require(session, user, analysis_id)
    comment = next((item for item in analysis.comments if item.id == comment_id), None)
    if comment is None:
        raise WorkflowError(404, "Comment not found")
    role = canonical_role(str(user["role"]))
    if comment.author != user["sub"] and role not in {"supervisor", "administrator"}:
        raise WorkflowError(403, "Only the author or a supervisor can resolve this thread")
    comment.resolved = resolved
    return _comment_out(comment)


def get_report(session: Session, user: dict, analysis_id: str) -> dict:
    analysis = _require(session, user, analysis_id)
    return _report_out(analysis.report)


def save_report(session: Session, user: dict, analysis_id: str, sections: dict) -> dict:
    analysis = _require(session, user, analysis_id)
    role = canonical_role(str(user["role"]))
    supervisor_notes = role == "supervisor" and analysis.status == "SUPERVISOR_REVIEW"
    if not supervisor_notes:
        _require_editor(user, analysis)
    report = analysis.report
    if supervisor_notes:
        for key in SECTION_KEYS:
            if key == "reviewer_notes":
                continue
            incoming = sections.get(key) or {}
            if str(incoming.get("text", report.current_body[key]["text"])) != report.current_body[key]["text"]:
                raise WorkflowError(403, "Supervisors can add reviewer notes without rewriting the draft")
    original = report.ai_original
    merged = {}
    for key in SECTION_KEYS:
        incoming = sections.get(key) or {}
        text = str(incoming.get("text", report.current_body[key]["text"]))
        origin = "human" if text != original[key]["text"] else original[key]["origin"]
        merged[key] = {"text": text, "origin": origin}
    if merged != report.current_body:
        report.current_body = merged
        flag_modified(report, "current_body")
        report.updated_at = datetime.now(timezone.utc)
        session.add(ReportRevision(
            id=str(uuid4()), report_id=report.id, author=str(user["sub"]), kind="human_edit",
            body=merged, created_at=report.updated_at,
        ))
        _audit(session, str(user["sub"]), "REPORT_EDITED", "report", report.id, {"analysis_id": analysis.id})
        if analysis.status == "AI_SCREENING_COMPLETE":
            analysis.status = "INVESTIGATOR_REVIEW"
    session.flush()
    session.refresh(report)
    return _report_out(report)


def report_diff(session: Session, user: dict, analysis_id: str) -> list[dict]:
    analysis = _require(session, user, analysis_id)
    report = analysis.report
    diffs = []
    for key, label in SECTIONS:
        ai_text = report.ai_original[key]["text"]
        current_text = report.current_body[key]["text"]
        diffs.append({
            "section": key, "label": label, "ai_text": ai_text, "current_text": current_text,
            "changed": ai_text != current_text, "current_origin": report.current_body[key]["origin"],
        })
    return diffs


def restore_revision(session: Session, user: dict, analysis_id: str, revision_id: str) -> dict:
    analysis = _require(session, user, analysis_id)
    _require_editor(user, analysis)
    report = analysis.report
    revision = session.get(ReportRevision, revision_id)
    if revision is None or revision.report_id != report.id:
        raise WorkflowError(404, "Revision not found")
    report.current_body = revision.body
    flag_modified(report, "current_body")
    report.updated_at = datetime.now(timezone.utc)
    session.add(ReportRevision(
        id=str(uuid4()), report_id=report.id, author=str(user["sub"]), kind="restore",
        body=revision.body, created_at=report.updated_at,
    ))
    _audit(session, str(user["sub"]), "REPORT_EDITED", "report", report.id, {"restored_from": revision_id})
    return _report_out(report)


def submit_report(session: Session, user: dict, analysis_id: str) -> dict:
    analysis = _require(session, user, analysis_id)
    _require_editor(user, analysis)
    if analysis.status not in EDITABLE_STATUSES:
        raise WorkflowError(409, "This report cannot be submitted from its current state")
    analysis.status = "SUPERVISOR_REVIEW"
    analysis.report.status = "submitted"
    session.add(ReviewAssignment(
        id=str(uuid4()), analysis_id=analysis.id, assignee_username=settings.supervisor_username,
        role_name="supervisor", purpose="report_approval", created_at=datetime.now(timezone.utc),
    ))
    _audit(session, str(user["sub"]), "REPORT_SUBMITTED", "report", analysis.report.id, {})
    return _detail(analysis)


def request_changes(session: Session, user: dict, analysis_id: str, body: str) -> dict:
    analysis = _require(session, user, analysis_id)
    if canonical_role(str(user["role"])) != "supervisor":
        raise WorkflowError(403, "Supervisor access required")
    if analysis.status != "SUPERVISOR_REVIEW":
        raise WorkflowError(409, "Report is not awaiting supervisor review")
    text = body.strip()
    if not text:
        raise WorkflowError(422, "Describe the requested changes")
    analysis.status = "CHANGES_REQUESTED"
    analysis.report.status = "changes_requested"
    comment = Comment(
        id=str(uuid4()), analysis_id=analysis.id, report_id=analysis.report.id,
        author=str(user["sub"]), author_role="supervisor", body=text, mentions=mentions_in(text),
        resolved=False, created_at=datetime.now(timezone.utc),
    )
    analysis.comments.append(comment)
    _audit(session, str(user["sub"]), "COMMENT_CREATED", "comment", comment.id, {"purpose": "changes_requested"})
    return _detail(analysis)


def finalize_report(session: Session, user: dict, analysis_id: str) -> dict:
    analysis = _require(session, user, analysis_id)
    if canonical_role(str(user["role"])) != "supervisor":
        raise WorkflowError(403, "Supervisor access required")
    if analysis.status != "SUPERVISOR_REVIEW":
        raise WorkflowError(409, "Report is not awaiting approval")
    analysis.status = "FINALIZED"
    analysis.report.status = "finalized"
    _audit(session, str(user["sub"]), "REPORT_APPROVED", "report", analysis.report.id, {})
    _audit(session, str(user["sub"]), "REPORT_FINALIZED", "report", analysis.report.id, {})
    return _detail(analysis)


def ask(session: Session, user: dict, analysis_id: str, question: str, history: list[dict] | None = None) -> dict:
    analysis = _require(session, user, analysis_id)
    media = analysis.media_files[0] if analysis.media_files else None
    original = analysis.report.ai_original if analysis.report and analysis.report.ai_original else {}
    excerpt = "\n".join(
        f"{key}: {original[key]['text']}"
        for key in ("automated_screening_results", "audio_findings", "video_findings")
        if key in original and isinstance(original[key], dict)
    )
    context = {
        "findings": [_assistant_finding(item) for item in analysis.findings],
        "media_path": _assistant_media_path(media),
        "content_type": media.content_type if media else None,
        "report_excerpt": excerpt,
        "history": [{"role": turn["role"], "text": turn["text"]} for turn in (history or [])],
    }
    if settings.assistant_provider == "bedrock":
        return _bedrock_answer(session, analysis, media, question, context)
    return _assistant().answer(question, context)


def _assistant_media_path(media: MediaFile | None) -> str | None:
    """Local copy of the recording for media-aware assistants; the rules assistant never reads it."""
    if media is None or settings.assistant_provider == "rules":
        return None
    from deeptrace.storage import resolve_media
    path = resolve_media(media.storage_key)
    return str(path) if path else None


def _assistant():
    if settings.assistant_provider == "gemini" and settings.gemini_api_key:
        from deeptrace.ml.gemini_assistant import GeminiCaseAssistant
        return GeminiCaseAssistant(settings.gemini_api_key, settings.gemini_model)
    return assistant


def _bedrock_answer(session: Session, analysis: Analysis, media: MediaFile | None, question: str, context: dict) -> dict:
    """Video model describes the recording once (cached); answer model replies from that and the case record."""
    from deeptrace.ml.bedrock_assistant import (
        TIMELINE_PROMPT_VERSION, BedrockCaseAssistant, NovaVideoObserver, bedrock_client, video_block,
    )
    try:
        client = bedrock_client(settings.bedrock_region or settings.aws_region)
    except Exception as exc:  # boto3 missing or no credentials/region
        logger.info("bedrock_client_unavailable %s", type(exc).__name__)
        return assistant.answer(question, context)
    observer = NovaVideoObserver(client, settings.bedrock_video_model)
    from deeptrace.storage import s3_uri
    video = video_block(context["media_path"], context["content_type"], s3_uri(media.storage_key)) if media else None
    context["video"] = video
    if video is not None and media is not None:
        context["observations"] = _media_observations(session, analysis, media, observer, video, TIMELINE_PROMPT_VERSION)
    return BedrockCaseAssistant(client, settings.bedrock_answer_model, observer).answer(question, context)


def _media_observations(session: Session, analysis: Analysis, media: MediaFile, observer, video: dict, version: str) -> dict | None:
    cached = session.scalar(select(MediaObservation).where(
        MediaObservation.analysis_id == analysis.id, MediaObservation.media_sha256 == media.sha256,
        MediaObservation.model_id == observer.model_id, MediaObservation.prompt_version == version,
    ).order_by(MediaObservation.created_at.desc()).limit(1))
    if cached is not None:
        return cached.observations
    try:
        observations = observer.timeline(video)
    except Exception as exc:  # Bedrock errors: answer without a timeline and try again on the next question
        logger.info("bedrock_timeline_unavailable %s", type(exc).__name__)
        return None
    session.add(MediaObservation(
        id=str(uuid4()), analysis_id=analysis.id, media_sha256=media.sha256, model_id=observer.model_id,
        prompt_version=version, observations=observations, created_at=datetime.now(timezone.utc),
    ))
    session.flush()
    return observations


def list_audit(session: Session, user: dict, analysis_id: str | None) -> list[dict]:
    role = canonical_role(str(user["role"]))
    if role == "forensic_reviewer":
        raise WorkflowError(403, "Audit history is available to supervisors and administrators")
    events = list(session.scalars(select(AuditEvent).order_by(AuditEvent.timestamp.desc()).limit(500)))
    if analysis_id:
        analysis = _require(session, user, analysis_id)
        related = {analysis.id, analysis.report.id}
        related.update(item.id for item in analysis.findings)
        related.update(item.id for item in analysis.comments)
        events = [
            event for event in events
            if event.entity_id in related or (event.event_metadata or {}).get("analysis_id") == analysis.id
        ]
    elif role == "investigator":
        owned = set(session.scalars(select(Analysis.id).join(User).where(User.username == user["sub"])))
        events = [
            event for event in events
            if event.entity_id in owned or (event.event_metadata or {}).get("analysis_id") in owned
        ]
    elif role not in {"supervisor", "administrator"}:
        raise WorkflowError(403, "Audit history is not available for this role")
    return [_audit_out(event) for event in events[:200]]


def model_info() -> dict:
    return {
        "video_model": settings.video_model,
        "video_configured": bool(settings.efficientnet_command if settings.video_model == "efficientnetb4" else settings.effort_command),
        "scene_model": "community_forensics",
        "scene_configured": bool(settings.scene_command),
        "audio_model": settings.audio_model,
        "audio_configured": bool(settings.nes2net_command if settings.audio_model == "nes2net" else settings.aasist_command),
        "supplementary_methods": [
            {"task": "GAN artifacts", "model": "CNNDetection ResNet-50", "configured": bool(settings.gan_artifact_command), "kind": "detector"},
            {"task": "Vocoder artifacts", "model": "LFCC-LCNN (ASVspoof DF)", "configured": bool(settings.vocoder_artifact_command), "kind": "detector"},
            {"task": "Micro-expression intervals", "model": "SOFTNet (CASME micro s1)", "configured": bool(settings.micro_expression_command), "kind": "interval_spotter"},
        ],
        "decision_threshold": settings.decision_threshold,
        "face_decision_rule": settings.efficientnet_decision_rule if settings.video_model == "efficientnetb4" else "default_0_5",
        "face_decision_threshold": EFFICIENTNET_RULES[settings.efficientnet_decision_rule][0] if settings.video_model == "efficientnetb4" else 0.5,
        "calibration_version": None,
        "preprocessing": {
            "video": f"jpeg every {settings.frame_interval_seconds}s, max {settings.max_frames} frames",
            "audio": "mono 16 kHz PCM when extracted from video",
        },
        "limitation": LIMITATION,
        "note": "Calibrated probability is omitted until a calibration procedure is fitted and versioned for the checkpoint.",
    }


def delete_analysis_for_report(session: Session, user: dict, legacy_report_id: str) -> list[str]:
    analysis = session.scalar(
        select(Analysis).where(Analysis.legacy_report_id == legacy_report_id).options(
            selectinload(Analysis.owner), selectinload(Analysis.media_files), selectinload(Analysis.model_runs),
            selectinload(Analysis.findings).selectinload(Finding.reviews),
            selectinload(Analysis.findings).selectinload(Finding.attribution),
            selectinload(Analysis.comments), selectinload(Analysis.report).selectinload(Report.revisions),
            selectinload(Analysis.assignments),
        )
    )
    if analysis is None:
        return []
    if canonical_role(str(user["role"])) != "administrator" and analysis.owner.username != user["sub"]:
        raise WorkflowError(403, "Only the report owner can delete it")
    paths = [item.storage_key for item in analysis.media_files]
    _audit(session, str(user["sub"]), "REPORT_DELETED", "analysis", analysis.id, {"legacy_report_id": legacy_report_id})
    for comment in analysis.comments:
        comment.parent_id = None
        comment.finding_id = None
        comment.report_id = None
    session.flush()
    for comment in list(analysis.comments):
        session.delete(comment)
    for finding in analysis.findings:
        for review in list(finding.reviews):
            session.delete(review)
        if finding.attribution:
            session.delete(finding.attribution)
    session.flush()
    for finding in list(analysis.findings):
        session.delete(finding)
    for run in list(analysis.model_runs):
        session.delete(run)
    if analysis.report:
        for revision in list(analysis.report.revisions):
            session.delete(revision)
        session.delete(analysis.report)
    for assignment in list(analysis.assignments):
        session.delete(assignment)
    for observation in session.scalars(select(MediaObservation).where(MediaObservation.analysis_id == analysis.id)):
        session.delete(observation)
    for media in list(analysis.media_files):
        session.delete(media)
    session.delete(analysis)
    return paths


def list_users(session: Session, user: dict) -> list[dict]:
    _require_admin(user)
    return [display_user(item) for item in session.scalars(select(User).order_by(User.username))]


def create_user(session: Session, actor: dict, username: str, password: str, role: str, display_name: str) -> dict:
    _require_admin(actor)
    if role not in ROLES:
        raise WorkflowError(422, "Unknown role")
    if session.scalar(select(User).where(User.username == username)):
        raise WorkflowError(409, "That username already exists")
    created = User(
        id=str(uuid4()), username=username, display_name=display_name or username,
        password_hash=hash_password(password), role_name=role, active=True,
        created_at=datetime.now(timezone.utc),
    )
    session.add(created)
    session.flush()
    return display_user(created)


def update_user_role(session: Session, actor: dict, username: str, role: str) -> dict:
    _require_admin(actor)
    if role not in ROLES:
        raise WorkflowError(422, "Unknown role")
    account = session.scalar(select(User).where(User.username == username))
    if account is None:
        raise WorkflowError(404, "User not found")
    account.role_name = role
    return display_user(account)


def authenticate_directory_user(session: Session, username: str, password: str) -> str | None:
    account = session.scalar(select(User).where(User.username == username, User.active.is_(True)))
    if account is None or not account.password_hash:
        return None
    from deeptrace.workflow.access import verify_password
    if not verify_password(password, account.password_hash):
        return None
    return account.role_name


def _ensure_user(session: Session, username: str, role: str) -> User:
    account = session.scalar(select(User).where(User.username == username))
    if account:
        return account
    stored = canonical_role(role)
    if stored not in ROLES:
        stored = "investigator"
    account = User(
        id=str(uuid4()), username=username, display_name=username, password_hash=None,
        role_name=stored, active=True, created_at=datetime.now(timezone.utc),
    )
    session.add(account)
    session.flush()
    return account


def _require(session: Session, user: dict, analysis_id: str) -> Analysis:
    analysis = session.scalar(
        select(Analysis).where(Analysis.id == analysis_id).options(
            selectinload(Analysis.owner), selectinload(Analysis.media_files),
            selectinload(Analysis.model_runs), selectinload(Analysis.findings).selectinload(Finding.reviews),
            selectinload(Analysis.findings).selectinload(Finding.attribution),
            selectinload(Analysis.comments), selectinload(Analysis.report).selectinload(Report.revisions),
        )
    )
    if analysis is None or not can_read(user, analysis):
        raise WorkflowError(404, "Analysis not found")
    return analysis


def _require_editor(user: dict, analysis: Analysis) -> None:
    if canonical_role(str(user["role"])) != "investigator" or analysis.owner.username != user.get("sub"):
        raise WorkflowError(403, "Only the assigned investigator can edit this draft")
    if analysis.status not in EDITABLE_STATUSES:
        raise WorkflowError(409, "This report is not open for editing")


def _require_admin(user: dict) -> None:
    if canonical_role(str(user["role"])) != "administrator":
        raise WorkflowError(403, "Administrator access required")


def _visible_ids(session: Session, user: dict) -> set[str]:
    role = canonical_role(str(user["role"]))
    stmt = select(Analysis.id)
    if role == "investigator":
        stmt = stmt.join(User).where(User.username == user["sub"])
    elif role == "forensic_reviewer":
        stmt = stmt.where(Analysis.status == "EXPERT_REVIEW_REQUESTED")
    elif role not in {"supervisor", "administrator"}:
        return set()
    return set(session.scalars(stmt))


def _summaries(session: Session, user: dict, *, statuses: list[str], owner: str | None = None) -> list[dict]:
    stmt = select(Analysis).where(Analysis.status.in_(statuses)).options(
        selectinload(Analysis.owner), selectinload(Analysis.media_files), selectinload(Analysis.findings),
    ).order_by(Analysis.created_at.desc())
    if owner:
        stmt = stmt.join(User).where(User.username == owner)
    rows = []
    for analysis in session.scalars(stmt).unique():
        if can_read(user, analysis):
            rows.append(_summary(analysis))
    return rows


def _load_many(session: Session, ids: set[str]) -> list[Analysis]:
    stmt = select(Analysis).where(Analysis.id.in_(ids)).options(
        selectinload(Analysis.owner), selectinload(Analysis.media_files), selectinload(Analysis.findings),
    ).order_by(Analysis.created_at.desc())
    return list(session.scalars(stmt).unique())


def _summary(analysis: Analysis) -> dict:
    media = analysis.media_files[0] if analysis.media_files else None
    return {
        "id": analysis.id, "title": analysis.title, "status": analysis.status,
        "owner": analysis.owner.username, "media_kind": media.media_kind if media else "audio",
        "created_at": analysis.created_at, "finding_count": len(analysis.findings),
        "legacy_report_id": analysis.legacy_report_id,
    }


def _detail(analysis: Analysis) -> dict:
    media = analysis.media_files[0]
    payload = _summary(analysis)
    payload.update({
        "media": {
            "filename": media.filename, "media_kind": media.media_kind, "content_type": media.content_type,
            "size_bytes": media.size_bytes, "sha256": media.sha256, "duration_seconds": media.duration_seconds,
            "container": media.container,
        },
        "model_runs": [_model_run_out(item) for item in analysis.model_runs],
        "findings": [_finding_out(item) for item in sorted(analysis.findings, key=_finding_order)],
        "comments": [_comment_out(item) for item in sorted(analysis.comments, key=lambda item: _when(item.created_at))],
        "limitation": LIMITATION,
        "development_mock": any(bool((item.run_metadata or {}).get("development_mock")) for item in analysis.model_runs),
        "review_checks": [check for item in analysis.model_runs for check in (item.run_metadata or {}).get("review_checks", [])],
    })
    return payload


def _model_run_out(item: ModelRun) -> dict:
    return {
        "id": item.id, "modality": item.modality, "model_name": item.model_name,
        "model_version": item.model_version, "checkpoint": item.checkpoint,
        "preprocessing_version": item.preprocessing_version, "status": item.status,
        "threshold": item.threshold, "raw_score": item.raw_score,
        "calibrated_probability": item.calibrated_probability, "calibration_version": item.calibration_version,
        "notes": item.notes or [], "development_mock": bool((item.run_metadata or {}).get("development_mock")),
        "coverage": (item.run_metadata or {}).get("coverage"),
        "coverage_limited": bool((item.run_metadata or {}).get("coverage_limited")),
    }


def _finding_out(item: Finding) -> dict:
    attribution = None
    if item.attribution:
        attribution = {
            "method": item.attribution.method, "available": item.attribution.available,
            "summary": item.attribution.summary, "metadata": item.attribution.artifact_metadata or {},
        }
    return {
        "id": item.id, "modality": item.modality, "start_time": item.start_time, "end_time": item.end_time,
        "model_name": item.model_name, "model_version": item.model_version,
        "preprocessing_version": item.preprocessing_version, "raw_logits": item.raw_logits,
        "raw_score": item.raw_score, "normalized_score": item.normalized_score,
        "calibrated_probability": item.calibrated_probability, "threshold": item.threshold,
        "predicted_class": item.predicted_class, "attribution_method": item.attribution_method,
        "score_scope": item.score_scope, "human_disposition": item.human_disposition,
        "attribution": attribution,
        "reviews": [{
            "id": review.id, "actor_id": review.actor_id, "previous_value": review.previous_value,
            "new_value": review.new_value, "comment": review.comment, "created_at": review.created_at,
        } for review in sorted(item.reviews, key=lambda review: _when(review.created_at))],
    }


def _comment_out(item: Comment) -> dict:
    return {
        "id": item.id, "author": item.author, "author_role": item.author_role, "body": item.body,
        "finding_id": item.finding_id, "parent_id": item.parent_id, "timestamp_seconds": item.timestamp_seconds,
        "mentions": item.mentions or [], "resolved": item.resolved, "created_at": item.created_at,
    }


def _report_out(report: Report) -> dict:
    return {
        "id": report.id, "analysis_id": report.analysis_id, "status": report.status,
        "ai_original": report.ai_original, "current": report.current_body,
        "revisions": [{
            "id": item.id, "author": item.author, "kind": item.kind, "created_at": item.created_at,
        } for item in sorted(report.revisions, key=lambda item: _when(item.created_at))],
    }


def _audit_out(event: AuditEvent) -> dict:
    return {
        "id": event.id, "actor_id": event.actor_id, "action": event.action,
        "entity_type": event.entity_type, "entity_id": event.entity_id,
        "timestamp": event.timestamp, "metadata": event.event_metadata or {},
    }


def _assistant_finding(item: Finding) -> dict:
    metadata = item.attribution.artifact_metadata if item.attribution and item.attribution.artifact_metadata else {}
    windows = metadata.get("windows") if isinstance(metadata, dict) else None
    stored = []
    if isinstance(windows, list):
        for window in windows:
            if isinstance(window, dict) and {"start", "end", "score_delta"} <= window.keys():
                stored.append({
                    "start": window["start"], "end": window["end"], "score_delta": window["score_delta"],
                    "fill": window.get("fill"),
                })
    return {
        "id": item.id, "modality": item.modality, "start_time": item.start_time, "end_time": item.end_time,
        "raw_score": item.raw_score, "human_disposition": item.human_disposition,
        "attribution_method": item.attribution_method,
        "windows": stored,
        "fill_rankings_agree": metadata.get("fill_rankings_agree") if isinstance(metadata, dict) else None,
    }


def _explain(modality: str, attribution: dict) -> dict:
    from deeptrace.ml.explainers import AASISTTemporalOcclusionExplainer, EfficientNetGradCAMExplainer
    payload = attribution or {}
    if modality == "video":
        return EfficientNetGradCAMExplainer().explain(payload)
    temporal = AASISTTemporalOcclusionExplainer().explain(payload)
    if temporal["available"]:
        return temporal
    return AASISTAudioAttribution().explain(
        temporal=payload.get("temporal_relevance"),
        spectral=payload.get("spectral_relevance"),
        attention=payload.get("graph_attention"),
    )


def _preprocessing(modality: str) -> str:
    if modality == "video":
        return f"jpeg@{settings.frame_interval_seconds}s/max{settings.max_frames}"
    return "pcm-16k-mono"


TASK_LABELS = {
    "face_manipulation": "Face manipulation",
    "synthetic_video": "AI-generated video",
    "audio_spoof": "Synthetic speech",
}


def _finding_order(item: Finding) -> tuple:
    return (item.start_time, item.modality, item.model_name, item.id)


def _finding_runs(findings: list[Finding]) -> list[dict]:
    """Group per-window findings into contiguous spans per model, keeping the case numbering."""
    runs: list[dict] = []
    for number, item in enumerate(sorted(findings, key=_finding_order), start=1):
        end = item.end_time if item.end_time is not None else item.start_time
        run = next((entry for entry in reversed(runs) if entry["model"] == item.model_name), None)
        if run and item.start_time <= run["end"] + 0.05:
            run["numbers"].append(number)
            run["end"] = max(run["end"], end)
            run["peak"] = max(run["peak"], item.raw_score)
            continue
        runs.append({
            "model": item.model_name, "modality": item.modality, "start": item.start_time, "end": end,
            "peak": item.raw_score, "threshold": item.threshold, "numbers": [number],
        })
    return sorted(runs, key=lambda entry: entry["start"])


def _numbers(values: list[int]) -> str:
    if len(values) == 1:
        return f"Finding {values[0]}"
    spans: list[list[int]] = []
    for value in values:
        if spans and value == spans[-1][-1] + 1:
            spans[-1].append(value)
        else:
            spans.append([value])
    return "Findings " + ", ".join(str(span[0]) if len(span) == 1 else f"{span[0]}–{span[-1]}" for span in spans)


def _draft_report(report: AdvisoryReport, findings: list[Finding]) -> dict[str, dict]:
    def lines(modality: str) -> str:
        runs = [run for run in _finding_runs(findings) if run["modality"] == modality]
        if not runs:
            return "No automated finding exceeded the decision threshold. This does not establish authenticity."
        return "\n".join(
            f"{_numbers(run['numbers'])}, {_clock(run['start'])}–{_clock(run['end'])}: {run['model']} scored "
            f"{len(run['numbers'])} {'window' if len(run['numbers']) == 1 else 'windows'} at or above the "
            f"{run['threshold']:.2f} decision threshold (peak model screening score {run['peak']:.2f}). "
            "Possible manipulation signal for human review."
            for run in runs
        )

    def model_line(item) -> str:
        task = TASK_LABELS.get(item.task or "", item.component.capitalize())
        score = item.raw_score if item.raw_score is not None else item.synthetic_confidence
        scored = "not produced" if score is None else f"{score:.2f}"
        return f"{task}: {item.detector_name or item.model_name}, version {item.model_version}. Model screening score {scored}."

    models = "\n".join(model_line(item) for item in report.components)
    if report.review_checks:
        models += "\nSupplementary review measurements (not manipulation classifiers):\n" + "\n".join(
            f"{item.title}: {item.status}; {item.method} ({item.version}). {item.summary}" for item in report.review_checks)
    body = {
        "analysis_information": f"{report.media.filename}. {report.examination_scope}",
        "media_information": (
            f"{report.media.filename} ({report.media.media_kind}, {report.media.size_bytes / 1_000_000:.1f} MB, "
            f"{'duration not available' if report.media.duration_seconds is None else f'{report.media.duration_seconds:.1f} s'}).\n"
            f"SHA-256 {report.media.sha256}. The hash identifies the received bytes only."
        ),
        "models_used": models,
        "automated_screening_results": report.summary,
        "audio_findings": lines("audio"),
        "video_findings": lines("video"),
        "investigator_assessment": "",
        "items_requiring_additional_review": "",
        "limitations": "\n".join(report.limitations),
        "reviewer_notes": "",
    }
    return {
        key: {"text": text, "origin": "human" if key in HUMAN_SECTIONS else "ai"}
        for key, text in body.items()
    }


def _when(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _clock(value: float | None) -> str:
    if value is None:
        return "—"
    minutes, seconds = divmod(max(value, 0), 60)
    return f"{int(minutes):02d}:{seconds:04.1f}"


def _audit(session: Session, actor: str, action: str, entity_type: str, entity_id: str, metadata: dict) -> None:
    session.add(AuditEvent(
        id=str(uuid4()), actor_id=actor, action=action, entity_type=entity_type,
        entity_id=entity_id, timestamp=datetime.now(timezone.utc), event_metadata=metadata,
    ))
