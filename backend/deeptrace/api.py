import os
import tempfile
import sqlite3
from concurrent.futures import ThreadPoolExecutor, wait
from functools import partial
from time import perf_counter
from pathlib import Path
from urllib.parse import urlsplit
from sqlalchemy.exc import SQLAlchemyError

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from deeptrace.analyzers import (
    AASISTAudioAnalyzer, CombinedVideoAnalyzer, EfficientNetVideoAnalyzer, EffortVideoAnalyzer, Nes2NetAudioAnalyzer,
    SceneVideoAnalyzer,
)
from deeptrace.analyzers.review_signals import analyze_micro_expression, analyze_review_signals
from deeptrace.analyzers.artifacts import GANArtifactAnalyzer, VocoderArtifactAnalyzer
from deeptrace.auth import employee_login, local_auto_login_available, require_user
from deeptrace.config import settings
from deeptrace.media import cleanup_prepared, extract_metadata, prepare_video
from deeptrace.profiling import AnalysisProfile
from deeptrace.schemas import (
    AdvisoryReport, CommentCreate, CommentResponse, ComponentResult, LoginRequest, LoginResponse,
    NotebookResponse, NotebookUpdate, ProfileResponse, ProfileUpdate,
)
from deeptrace.reporting import build_report
from deeptrace.db.session import session_scope
from deeptrace.report_store import (
    add_comment, can_access_report, delete_report, get_media_path, get_notebook, get_profile, get_report,
    list_comments, list_reports, persist_media, report_owner, save_notebook, save_report, submit_report,
    transition_review, update_profile,
)
from deeptrace.workflow import service as workflow_service
from deeptrace.workflow.access import WorkflowError

router = APIRouter()
_review_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="deeptrace-review")


@router.get("/v1/auth/config")
def auth_config() -> dict[str, str | bool | None]:
    return {"enabled": settings.auth_enabled, "mode": settings.auth_mode, "domain": settings.cognito_domain,
        "client_id": settings.cognito_app_client_id, "redirect_uri": settings.cognito_redirect_uri,
        "local_auto_login": local_auto_login_available()}


@router.post("/v1/auth/login", response_model=LoginResponse)
def login(credentials: LoginRequest) -> LoginResponse:
    if not settings.auth_enabled or settings.auth_mode != "employee":
        raise HTTPException(status_code=404, detail="Employee login is not enabled")
    token, role = employee_login(credentials.username, credentials.password)
    return LoginResponse(access_token=token, expires_in=settings.token_minutes * 60, role=role)


@router.post('/v1/auth/local-login', response_model=LoginResponse)
def local_login(request: Request) -> LoginResponse:
    if not local_auto_login_available():
        raise HTTPException(status_code=404, detail='Local automatic login is not enabled')
    origin = request.headers.get('origin')
    loopback = {'localhost', '127.0.0.1', '::1'}
    if request.url.hostname not in loopback or (origin and (origin not in settings.frontend_origins or urlsplit(origin).hostname not in loopback)):
        raise HTTPException(status_code=403, detail='Local automatic login requires a local application origin')
    token, role = employee_login(settings.employee_username or '', settings.employee_password or '')
    response = LoginResponse(access_token=token, expires_in=settings.token_minutes * 60, role=role)
    return response


@router.post("/v1/analyze", response_model=AdvisoryReport)
async def analyze(file: UploadFile = File(...), user: dict = Depends(require_user)) -> AdvisoryReport:
    profile = AnalysisProfile()
    profile.log_start()
    content_type = file.content_type or "application/octet-stream"
    suffix = Path(file.filename or "upload").suffix
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    fd, raw_path = tempfile.mkstemp(prefix="deeptrace-", suffix=suffix, dir=settings.upload_dir)
    path = Path(raw_path)
    size = 0
    try:
        with os.fdopen(fd, "wb") as target:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > settings.max_upload_mb * 1024 * 1024:
                    raise HTTPException(status_code=413, detail="Upload exceeds configured size limit")
                target.write(chunk)
        profile.add("upload/save", perf_counter() - profile.started)
        return await run_in_threadpool(_screen_upload, path, Path(file.filename or "upload").name, content_type, user, profile)
    finally:
        await file.close()
        if not settings.keep_uploads:
            path.unlink(missing_ok=True)
        profile.log()


def _screen_upload(path: Path, filename: str, content_type: str, user: dict,
                   profile: AnalysisProfile | None = None) -> AdvisoryReport:
    profile = profile or AnalysisProfile()
    prepared_frames = None
    review_future = micro_future = None
    try:
        try:
            media_timings = {}
            metadata = extract_metadata(path, filename, content_type, settings.ffprobe_path,
                profile.metadata, media_timings)
            for name, elapsed in media_timings.items():
                profile.add(name, elapsed)
        except ValueError as exc:
            raise HTTPException(status_code=415, detail=str(exc)) from exc
        review = partial(analyze_review_signals, settings.review_signals_command, path, metadata,
                         settings.review_signals_timeout_seconds)
        micro = None
        if settings.micro_expression_command:
            micro = partial(analyze_micro_expression, settings.micro_expression_command, path, metadata)
        if settings.parallel_review_checks and metadata.media_kind == "video":
            if settings.review_signals_command:
                review_future = _review_executor.submit(review)
            if micro is not None:
                micro_future = _review_executor.submit(micro)
        face_analyzer = (EfficientNetVideoAnalyzer(settings.efficientnet_command, settings.frame_interval_seconds,
            explain=settings.explain, decision_rule=settings.efficientnet_decision_rule)
            if settings.video_model == "efficientnetb4" else EffortVideoAnalyzer(settings.effort_command, settings.frame_interval_seconds))
        scene_analyzer = SceneVideoAnalyzer(settings.scene_command, settings.frame_interval_seconds)
        audio = (Nes2NetAudioAnalyzer(settings.nes2net_command) if settings.audio_model == "nes2net"
            else AASISTAudioAnalyzer(settings.aasist_command, settings.audio_model, settings.aasist_window_mode))
        if metadata.media_kind == "video":
            media_timings = {}
            preparation_error = None
            try:
                prepared_frames, extracted_audio = prepare_video(path, settings.ffmpeg_path,
                    settings.frame_interval_seconds, settings.max_frames, media_timings, profile.metadata)
            except RuntimeError as exc:
                preparation_error = type(exc).__name__
                extracted_audio = None
                metadata.extraction_warnings.append("Video preparation could not complete; video checks are unavailable.")
            for name, elapsed in media_timings.items():
                profile.add(name, elapsed)
            started = perf_counter()
            face_result = (face_analyzer.analyze(prepared_frames, metadata) if not preparation_error else
                ComponentResult(component="video", status="error", model_name=face_analyzer.model_name,
                    model_version="not_run", task="face_manipulation", notes=["Video preparation failed; no frames were assessed."]))
            profile.add_runner(f"{face_analyzer.model_name} detector", perf_counter() - started, face_analyzer.last_profile)
            started = perf_counter()
            scene_result = (scene_analyzer.analyze(prepared_frames, metadata) if not preparation_error else
                ComponentResult(component="video", status="error", model_name=scene_analyzer.model_name,
                    model_version="not_run", task="synthetic_video", notes=["Video preparation failed; no frames were assessed."]))
            profile.add_runner("CommFor detector", perf_counter() - started, scene_analyzer.last_profile)
            started = perf_counter()
            if preparation_error:
                audio_result = audio.analyze(path, metadata)
            elif extracted_audio:
                audio_result = audio.analyze(extracted_audio, metadata)
            else:
                audio_expected = any(codec.startswith("audio:") for codec in metadata.codecs) or bool(metadata.extraction_warnings)
                audio_result = ComponentResult(component="audio", status="error" if audio_expected else "not_applicable",
                    model_name=audio.model_name, model_version="not_run", task="audio_spoof",
                    notes=["Audio extraction failed; no audio was assessed." if audio_expected else "No audio stream was reported by the media probe."])
            profile.add_runner(f"{audio.model_name} detector", perf_counter() - started, audio.last_profile)
        else:
            face_result = ComponentResult(component="video", status="not_applicable", model_name=face_analyzer.model_name,
                model_version="n/a", detector_id="deepfakebench_efficientnet_b4", task="face_manipulation")
            scene_result = ComponentResult(component="video", status="not_applicable", model_name=scene_analyzer.model_name,
                model_version="n/a", detector_id="community_forensics", task="synthetic_video")
            started = perf_counter()
            audio_result = audio.analyze(path, metadata)
            profile.add_runner(f"{audio.model_name} detector", perf_counter() - started, audio.last_profile)
        components = [face_result, scene_result, audio_result]
        for analyzer, applicable, source in (
            (GANArtifactAnalyzer(settings.gan_artifact_command, settings.frame_interval_seconds),
                metadata.media_kind == 'video', prepared_frames),
            (VocoderArtifactAnalyzer(settings.vocoder_artifact_command),
                audio_result.status != 'not_applicable',
                (extracted_audio or path) if metadata.media_kind == 'video' else path),
        ):
            if not analyzer.command:
                continue
            started = perf_counter()
            if not applicable or source is None:
                component = ComponentResult(component='video' if isinstance(analyzer, GANArtifactAnalyzer) else 'audio',
                    status='not_applicable' if not applicable else 'error', model_name=analyzer.model_name,
                    model_version='not_run', detector_id=analyzer.detector_id, task=analyzer.task,
                    notes=['No applicable media stream.' if not applicable else 'Frame preparation failed.'])
            else:
                component = analyzer.analyze(source, metadata)
            components.append(component)
            profile.add_runner(analyzer.model_name, perf_counter() - started, analyzer.last_profile)
        started = perf_counter()
        review_checks = review_future.result() if review_future is not None else review()
        if micro is not None:
            review_checks.append(micro_future.result() if micro_future is not None else micro())
        profile.add("supplementary review wait" if review_future or micro_future
                    else "supplementary review measurements", perf_counter() - started)
        started = perf_counter()
        report = build_report(metadata, components, keep_uploads=settings.keep_uploads,
            review_checks=review_checks,
            visual_weight=settings.visual_weight, processing_methods=[
            f"Video preparation requested: JPEG sampling every {settings.frame_interval_seconds}s, maximum {settings.max_frames} frames; mono 16 kHz audio extraction. Actual coverage and failures are recorded in component notes."
            if metadata.media_kind == "video" else "Audio passed to selected inference adapter; resampling and analyzed duration are recorded in component notes."])
        profile.add("aggregation/report build", perf_counter() - started)
        started = perf_counter()
        report.owner = str(user["sub"])
        report.processing = {"status": "incomplete" if any(c.status in {"error", "unavailable"} for c in components) else "completed",
            "supplementary_status": "partial" if any(c.status in {"error", "unavailable"} for c in review_checks) else "completed",
            "elapsed_seconds": round(perf_counter() - profile.started, 3), "media_storage": "pending", "workflow_storage": "pending", "report_storage": "pending"}
        try:
            stored_media = persist_media(settings.report_media_dir, report.report_id, path, report.media.filename)
            report.processing["media_storage"] = "saved"
        except OSError:
            stored_media = None
            report.processing["media_storage"] = "unavailable"
            report.limitations.append("The received media could not be retained; playback is unavailable. Save this report before leaving the page.")
        profile.add("persistence: media copy", perf_counter() - started)
        from deeptrace.db.session import session_scope
        from deeptrace.workflow.service import record_screening
        started = perf_counter()
        if stored_media is not None:
            try:
                with session_scope() as session:
                    report.analysis_id = record_screening(
                        session, owner=str(user["sub"]), role=str(user["role"]),
                        report=report, media_path=str(stored_media),
                    )
                report.processing["workflow_storage"] = "saved"
            except (OSError, SQLAlchemyError):
                report.analysis_id = None
                report.processing["workflow_storage"] = "unavailable"
                report.limitations.append("The review workspace could not be saved. Download this report and retry when storage is available.")
        else:
            report.processing["workflow_storage"] = "unavailable"
        profile.add("persistence: workflow DB", perf_counter() - started)
        started = perf_counter()
        try:
            report.processing["elapsed_seconds"] = round(perf_counter() - profile.started, 3)
            report.processing["report_storage"] = "saved"
            if stored_media is None:
                raise OSError("No retained media")
            save_report(settings.report_db_path, str(user["sub"]), report, stored_media)
        except (OSError, sqlite3.Error):
            report.processing["report_storage"] = "unavailable"
            report.limitations.append("Report history could not be saved. This report is available in the current response; download it before leaving.")
        profile.add("persistence: legacy DB", perf_counter() - started)
        return report
    finally:
        # Running checks still read the upload. Cancel queued work and wait before the route removes it.
        futures = [future for future in (review_future, micro_future)
                   if future is not None and not future.cancel()]
        if futures:
            wait(futures)
        if prepared_frames:
            cleanup_prepared(prepared_frames)


@router.get("/v1/reports")
def report_history(user: dict = Depends(require_user)) -> list[dict]:
    return list_reports(settings.report_db_path, str(user["sub"]), str(user["role"]))


@router.delete("/v1/reports/{report_id}", status_code=204)
def remove_report(report_id: str, user: dict = Depends(require_user)) -> None:
    owner = report_owner(settings.report_db_path, report_id)
    if owner is None:
        raise HTTPException(status_code=404, detail="Report not found")
    if user["role"] != "administrator" and owner != user["sub"]:
        raise HTTPException(status_code=403, detail="Only the report owner can delete it")
    try:
        with session_scope() as session:
            media_keys = workflow_service.delete_analysis_for_report(session, user, report_id)
    except WorkflowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    stored = delete_report(settings.report_db_path, report_id)
    if stored:
        Path(stored).unlink(missing_ok=True)
    for key in media_keys:
        Path(key).unlink(missing_ok=True)


@router.get("/v1/reports/{report_id}", response_model=AdvisoryReport)
def saved_report(report_id: str, user: dict = Depends(require_user)) -> AdvisoryReport:
    report = get_report(settings.report_db_path, str(user["sub"]), str(user["role"]), report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@router.post("/v1/reports/{report_id}/submit")
def send_for_review(report_id: str, user: dict = Depends(require_user)) -> dict[str, str]:
    if user["role"] != "analyst":
        raise HTTPException(status_code=403, detail="Only analysts can submit reports")
    if not settings.supervisor_username:
        raise HTTPException(status_code=503, detail="No review supervisor is configured")
    if not submit_report(
        settings.report_db_path, str(user["sub"]), report_id, settings.supervisor_username,
    ):
        raise HTTPException(status_code=409, detail="Report is unavailable or already submitted")
    return {"status": "submitted", "reviewer": settings.supervisor_username}


@router.post("/v1/reports/{report_id}/review/start")
def start_review(report_id: str, user: dict = Depends(require_user)) -> dict[str, str]:
    if user["role"] != "supervisor":
        raise HTTPException(status_code=403, detail="Supervisor access required")
    if not transition_review(
        settings.report_db_path, str(user["sub"]), report_id, "submitted", "in_review",
    ):
        raise HTTPException(status_code=409, detail="Report is unavailable or not awaiting review")
    return {"status": "in_review"}


@router.post("/v1/reports/{report_id}/review/complete")
def complete_review(report_id: str, user: dict = Depends(require_user)) -> dict[str, str]:
    if user["role"] != "supervisor":
        raise HTTPException(status_code=403, detail="Supervisor access required")
    if not transition_review(
        settings.report_db_path, str(user["sub"]), report_id, "in_review", "reviewed",
    ):
        raise HTTPException(status_code=409, detail="Report is unavailable or not in review")
    return {"status": "reviewed"}


def ensure_report_access(report_id: str, user: dict) -> None:
    if not can_access_report(
        settings.report_db_path, str(user["sub"]), str(user["role"]), report_id,
    ):
        raise HTTPException(status_code=404, detail="Report not found")


@router.get("/v1/reports/{report_id}/comments", response_model=list[CommentResponse])
def report_comments(report_id: str, user: dict = Depends(require_user)) -> list[CommentResponse]:
    ensure_report_access(report_id, user)
    return list_comments(settings.report_db_path, report_id)


@router.post("/v1/reports/{report_id}/comments", response_model=CommentResponse)
def create_report_comment(
    report_id: str, comment: CommentCreate, user: dict = Depends(require_user),
) -> CommentResponse:
    ensure_report_access(report_id, user)
    body = comment.body.strip()
    if not body:
        raise HTTPException(status_code=422, detail="Comment cannot be empty")
    return add_comment(
        settings.report_db_path, report_id, str(user["sub"]), str(user["role"]),
        body,
    )


@router.get("/v1/reports/{report_id}/notebook", response_model=NotebookResponse)
def report_notebook(report_id: str, user: dict = Depends(require_user)) -> NotebookResponse:
    ensure_report_access(report_id, user)
    return get_notebook(settings.report_db_path, report_id, str(user["sub"]))


@router.put("/v1/reports/{report_id}/notebook", response_model=NotebookResponse)
def update_report_notebook(
    report_id: str, notebook: NotebookUpdate, user: dict = Depends(require_user),
) -> NotebookResponse:
    ensure_report_access(report_id, user)
    return save_notebook(
        settings.report_db_path, report_id, str(user["sub"]), notebook.body,
    )


@router.get("/v1/reports/{report_id}/media")
def report_media(report_id: str, user: dict = Depends(require_user)) -> FileResponse:
    media_path = get_media_path(
        settings.report_db_path, str(user["sub"]), str(user["role"]), report_id,
    )
    if media_path is None or not media_path.is_file():
        raise HTTPException(status_code=404, detail="Media not found")
    return FileResponse(media_path, filename=media_path.name)


@router.get("/v1/profile", response_model=ProfileResponse)
def profile(user: dict = Depends(require_user)) -> ProfileResponse:
    return get_profile(settings.report_db_path, str(user["sub"]), str(user["role"]))


@router.patch("/v1/profile", response_model=ProfileResponse)
def edit_profile(update: ProfileUpdate, user: dict = Depends(require_user)) -> ProfileResponse:
    return update_profile(
        settings.report_db_path, str(user["sub"]), str(user["role"]),
        update.display_name, update.title,
    )
