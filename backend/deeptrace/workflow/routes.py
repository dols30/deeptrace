"""Workflow HTTP API. Authorization is enforced in the service layer."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from deeptrace.auth import require_user
from deeptrace.db.session import get_session
from deeptrace.workflow.access import WorkflowError
from deeptrace.workflow.schemas import (
    AnalysisDetail, AnalysisSummary, AssistantIn, AssistantOut, AuditOut, CommentIn, CommentOut,
    DashboardOut, DispositionIn, FindingOut, ModelInfo, ReportOut, ReportSave, RestoreIn,
    RoleUpdate, SectionDiff, UserIn, UserOut,
)
from deeptrace.workflow import service

router = APIRouter()


def _call(action):
    try:
        return action()
    except WorkflowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get("/v1/dashboard", response_model=DashboardOut)
def workflow_dashboard(user: dict = Depends(require_user), session: Session = Depends(get_session)) -> dict:
    return service.dashboard(session, user)


@router.get("/v1/queue", response_model=list[AnalysisSummary])
def workflow_queue(user: dict = Depends(require_user), session: Session = Depends(get_session)) -> list[dict]:
    return service.queue(session, user)


@router.get("/v1/search", response_model=list[AnalysisSummary])
def workflow_search(q: str, user: dict = Depends(require_user), session: Session = Depends(get_session)) -> list[dict]:
    return _call(lambda: service.search(session, user, q))


@router.get("/v1/analyses/{analysis_id}", response_model=AnalysisDetail)
def workflow_analysis(analysis_id: str, user: dict = Depends(require_user), session: Session = Depends(get_session)) -> dict:
    return _call(lambda: service.get_analysis(session, user, analysis_id))


@router.get("/v1/analyses/{analysis_id}/media")
def workflow_media(analysis_id: str, user: dict = Depends(require_user), session: Session = Depends(get_session)) -> FileResponse:
    path = _call(lambda: service.media_path(session, user, analysis_id))
    from pathlib import Path
    media = Path(path)
    if not media.is_file():
        raise HTTPException(status_code=404, detail="Media not found")
    return FileResponse(media, filename=media.name)


@router.post("/v1/analyses/{analysis_id}/findings/{finding_id}/reviews", response_model=FindingOut)
def workflow_review(
    analysis_id: str, finding_id: str, body: DispositionIn,
    user: dict = Depends(require_user), session: Session = Depends(get_session),
) -> dict:
    return _call(lambda: service.review_finding(session, user, analysis_id, finding_id, body.disposition, body.comment))


@router.post("/v1/analyses/{analysis_id}/comments", response_model=CommentOut)
def workflow_comment(
    analysis_id: str, body: CommentIn, user: dict = Depends(require_user), session: Session = Depends(get_session),
) -> dict:
    return _call(lambda: service.add_comment(
        session, user, analysis_id, body.body, body.finding_id, body.parent_id, body.timestamp_seconds,
    ))


@router.post("/v1/analyses/{analysis_id}/comments/{comment_id}/resolve", response_model=CommentOut)
def workflow_resolve(
    analysis_id: str, comment_id: str, resolved: bool = True,
    user: dict = Depends(require_user), session: Session = Depends(get_session),
) -> dict:
    return _call(lambda: service.resolve_comment(session, user, analysis_id, comment_id, resolved))


@router.get("/v1/analyses/{analysis_id}/report", response_model=ReportOut)
def workflow_report(analysis_id: str, user: dict = Depends(require_user), session: Session = Depends(get_session)) -> dict:
    return _call(lambda: service.get_report(session, user, analysis_id))


@router.put("/v1/analyses/{analysis_id}/report", response_model=ReportOut)
def workflow_save_report(
    analysis_id: str, body: ReportSave, user: dict = Depends(require_user), session: Session = Depends(get_session),
) -> dict:
    return _call(lambda: service.save_report(session, user, analysis_id, {key: value.model_dump() for key, value in body.sections.items()}))


@router.get("/v1/analyses/{analysis_id}/report/diff", response_model=list[SectionDiff])
def workflow_diff(analysis_id: str, user: dict = Depends(require_user), session: Session = Depends(get_session)) -> list[dict]:
    return _call(lambda: service.report_diff(session, user, analysis_id))


@router.post("/v1/analyses/{analysis_id}/report/restore", response_model=ReportOut)
def workflow_restore(
    analysis_id: str, body: RestoreIn, user: dict = Depends(require_user), session: Session = Depends(get_session),
) -> dict:
    return _call(lambda: service.restore_revision(session, user, analysis_id, body.revision_id))


@router.post("/v1/analyses/{analysis_id}/report/submit", response_model=AnalysisDetail)
def workflow_submit(analysis_id: str, user: dict = Depends(require_user), session: Session = Depends(get_session)) -> dict:
    return _call(lambda: service.submit_report(session, user, analysis_id))


@router.post("/v1/analyses/{analysis_id}/report/request-changes", response_model=AnalysisDetail)
def workflow_changes(
    analysis_id: str, body: CommentIn, user: dict = Depends(require_user), session: Session = Depends(get_session),
) -> dict:
    return _call(lambda: service.request_changes(session, user, analysis_id, body.body))


@router.post("/v1/analyses/{analysis_id}/report/finalize", response_model=AnalysisDetail)
def workflow_finalize(analysis_id: str, user: dict = Depends(require_user), session: Session = Depends(get_session)) -> dict:
    return _call(lambda: service.finalize_report(session, user, analysis_id))


@router.post("/v1/analyses/{analysis_id}/assistant", response_model=AssistantOut)
def workflow_assistant(
    analysis_id: str, body: AssistantIn, user: dict = Depends(require_user), session: Session = Depends(get_session),
) -> dict:
    return _call(lambda: service.ask(session, user, analysis_id, body.question, [turn.model_dump() for turn in body.history]))


@router.get("/v1/audit", response_model=list[AuditOut])
def workflow_audit(
    analysis_id: str | None = None, user: dict = Depends(require_user), session: Session = Depends(get_session),
) -> list[dict]:
    return _call(lambda: service.list_audit(session, user, analysis_id))


@router.get("/v1/settings/models", response_model=ModelInfo)
def workflow_models(user: dict = Depends(require_user)) -> dict:
    return service.model_info()


@router.get("/v1/users", response_model=list[UserOut])
def workflow_users(user: dict = Depends(require_user), session: Session = Depends(get_session)) -> list[dict]:
    return _call(lambda: service.list_users(session, user))


@router.post("/v1/users", response_model=UserOut)
def workflow_create_user(body: UserIn, user: dict = Depends(require_user), session: Session = Depends(get_session)) -> dict:
    return _call(lambda: service.create_user(session, user, body.username, body.password, body.role, body.display_name))


@router.patch("/v1/users/{username}", response_model=UserOut)
def workflow_update_user(
    username: str, body: RoleUpdate, user: dict = Depends(require_user), session: Session = Depends(get_session),
) -> dict:
    return _call(lambda: service.update_user_role(session, user, username, body.role))
