import io
import wave
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from deeptrace.main import app
from deeptrace.config import settings
from deeptrace import api

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_report_database(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(settings, "report_db_path", tmp_path / "deeptrace.db")
    monkeypatch.setattr(settings, "report_media_dir", tmp_path / "report-media")
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'workflow.db'}")
    from deeptrace.db.session import reset_engine
    reset_engine()


def synthetic_wav() -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b"\x00\x00" * 800)
    return output.getvalue()


def test_poc_face_threshold_round_trips_through_upload_report_and_workflow(monkeypatch,tmp_path):
    import json
    import sys
    from deeptrace.schemas import MediaMetadata
    from deeptrace.ml.decision_rules import EFFICIENTNET_POC_THRESHOLD
    from test_decision_rules import face_payload

    frames = tmp_path/"frames"
    frames.mkdir()
    bridge = tmp_path/"face_runner.py"
    bridge.write_text("import json; print("+repr(json.dumps(face_payload([.8,EFFICIENTNET_POC_THRESHOLD])))+")")
    monkeypatch.setattr(settings,"auth_enabled",False)
    monkeypatch.setattr(settings,"video_model","efficientnetb4")
    monkeypatch.setattr(settings,"efficientnet_decision_rule","ffpp_c23_kaggle_v1")
    monkeypatch.setattr(settings,"efficientnet_command",f'{sys.executable} "{bridge}" --frames {{frames_dir}}')
    monkeypatch.setattr(settings,"decision_threshold",.5)
    for name in ("scene_command","aasist_command","gan_artifact_command","vocoder_artifact_command","micro_expression_command","review_signals_command"):
        monkeypatch.setattr(settings,name,None)
    monkeypatch.setattr(api,"extract_metadata",lambda *_args,**_kwargs:MediaMetadata(filename="test.mp4",media_kind="video",content_type="video/mp4",size_bytes=5,sha256="a"*64))
    monkeypatch.setattr(api,"prepare_video",lambda *_args,**_kwargs:(frames,None))
    monkeypatch.setattr(api,"cleanup_prepared",lambda _path:None)
    response=client.post("/v1/analyze",files={"file":("test.mp4",b"video","video/mp4")})
    assert response.status_code == 200
    report=response.json()
    face=report["components"][0]
    assert face["threshold"] == EFFICIENTNET_POC_THRESHOLD
    assert face["timestamps_seconds"] == [1.]
    assert face["samples"][0]["predicted_class"] == "no_elevated_signal"
    detail=client.get(f"/v1/analyses/{report['analysis_id']}").json()
    assert len(detail["findings"]) == 1
    assert detail["findings"][0]["threshold"] == EFFICIENTNET_POC_THRESHOLD
    assert detail["findings"][0]["start_time"] == 1.
    assert detail["model_runs"][0]["threshold"] == EFFICIENTNET_POC_THRESHOLD
    saved=client.get(f"/v1/reports/{report['report_id']}").json()
    assert saved["components"][0]["threshold_source"] == "ffpp_c23_kaggle_v1_development_only_any_frame"
    info=client.get("/v1/settings/models").json()
    assert info["face_decision_threshold"] == EFFICIENTNET_POC_THRESHOLD
    assert info["decision_threshold"] == .5


def test_health() -> None:
    assert client.get("/health").json() == {"status": "ok"}


@pytest.mark.parametrize('parallel', [False, True])
def test_opt_in_artifacts_persist_with_the_existing_workflow(monkeypatch,tmp_path,parallel):
    import json
    import sys
    from threading import Event
    from deeptrace.schemas import MediaMetadata
    monkeypatch.setattr(settings,'auth_enabled',False)
    monkeypatch.setattr(settings, 'parallel_review_checks', parallel)
    for name in ('efficientnet_command','scene_command','aasist_command','review_signals_command'):
        monkeypatch.setattr(settings,name,None)
    def command(name,payload):
        p=tmp_path/(name+'.py')
        p.write_text('import json; print(json.dumps('+repr(payload)+'))')
        return f'{sys.executable} "{p}"'
    monkeypatch.setattr(settings,'gan_artifact_command',command('gan',{'samples':[
        {'path':'frame_000003.jpg','fake_probability':.9}], 'model_version':'pinned','checkpoint':'gan#sha256=x'}))
    monkeypatch.setattr(settings,'vocoder_artifact_command',command('vocoder',{'fake_probability':.7,
        'samples':[{'start_time':0,'end_time':3,'fake_probability':.7}],
        'model_version':'pinned','checkpoint':'lfcc#sha256=y'}))
    monkeypatch.setattr(settings,'micro_expression_command',command('micro',{
        'technique':'micro_expression','modality':'video','title':'Micro-expression intervals',
        'status':'measured','method':'SOFTNet','summary':'Candidate interval',
        'intervals':[{'start_time':1,'end_time':1.4,'regression_score':.6}]}))
    if parallel:
        review_started, softnet_started = Event(), Event()
        review = api.analyze_review_signals
        softnet = api.analyze_micro_expression
        gan = api.GANArtifactAnalyzer.analyze

        def record_review(_command, *args):
            review_started.set()
            return review(None, *args)

        def record_softnet(*args):
            softnet_started.set()
            return softnet(*args)

        def check_overlap(*args):
            assert review_started.wait(timeout=3)
            assert softnet_started.wait(timeout=3)
            return gan(*args)

        monkeypatch.setattr(settings, 'review_signals_command', 'test-review-runner')
        monkeypatch.setattr(api, 'analyze_review_signals', record_review)
        monkeypatch.setattr(api, 'analyze_micro_expression', record_softnet)
        monkeypatch.setattr(api.GANArtifactAnalyzer, 'analyze', check_overlap)
    monkeypatch.setattr(api,'extract_metadata',lambda *a,**kw: MediaMetadata(filename='test.mp4',media_kind='video',
        content_type='video/mp4',size_bytes=10,sha256='a'*64,duration_seconds=3))
    monkeypatch.setattr(api,'prepare_video',lambda *a,**kw:(tmp_path,tmp_path/'audio.wav'))
    monkeypatch.setattr(api,'cleanup_prepared',lambda *a:None)
    report=client.post('/v1/analyze',files={'file':('test.mp4',b'test','video/mp4')}).json()
    assert len(report['components']) == 5
    assert report['components'][3]['detector_id'] == 'cnn_gan_artifacts'
    assert report['components'][4]['detector_id'] == 'lfcc_lcnn_artifacts'
    assert report['overall_synthetic_confidence'] is None
    restored=client.get('/v1/reports/'+report['report_id']).json()
    assert restored['review_checks'][-1]['technique'] == 'micro_expression'
    detail=client.get('/v1/analyses/'+report['analysis_id']).json()
    assert len(detail['model_runs']) == 5
    assert any(check['technique'] == 'micro_expression' for check in detail['review_checks'])
    assert any(f['model_name'] == 'CNNDetection ResNet-50 (blur/JPEG)' and f['start_time'] == 2 for f in detail['findings'])


def test_video_preparation_failure_still_returns_incomplete_report(monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("decoder unavailable")
    monkeypatch.setattr(settings,"auth_enabled",False)
    monkeypatch.setattr(settings,"aasist_command",None)
    monkeypatch.setattr(settings,"review_signals_command",None)
    monkeypatch.setattr(api,"prepare_video",broken)
    response=client.post('/v1/analyze',files={'file':('broken.mp4',b'corrupted','video/mp4')})
    assert response.status_code == 200
    report=response.json()
    assert [c['status'] for c in report['components']] == ['error','error','unavailable']
    assert report['processing']['status'] == 'incomplete'
    assert report['overall_synthetic_confidence'] is None
    assert client.get('/v1/reports/'+report['report_id']).status_code == 200


def test_storage_failure_keeps_downloadable_response(monkeypatch):
    def broken(*args, **kwargs):
        raise OSError('storage unavailable')
    monkeypatch.setattr(settings,"auth_enabled",False)
    monkeypatch.setattr(settings,"aasist_command",None)
    monkeypatch.setattr(settings,"review_signals_command",None)
    monkeypatch.setattr(api,"persist_media",broken)
    response=client.post('/v1/analyze',files={'file':('synthetic.wav',synthetic_wav(),'audio/wav')})
    assert response.status_code == 200
    report=response.json()
    assert report['analysis_id'] is None
    assert report['processing']['media_storage'] == 'unavailable'
    assert report['processing']['report_storage'] == 'unavailable'
    assert any('download' in line.lower() or 'save this report' in line.lower() for line in report['limitations'])


def test_browser_missing_mime_accepts_known_poc_extension_only(monkeypatch):
    monkeypatch.setattr(settings,'auth_enabled',False)
    monkeypatch.setattr(settings,'aasist_command',None)
    response=client.post('/v1/analyze',files={'file':('synthetic.WAV',synthetic_wav(),'application/octet-stream')})
    assert response.status_code == 200
    assert response.json()['media']['content_type'] == 'audio/wav'
    assert client.post('/v1/analyze',files={'file':('file.txt',b'x','application/octet-stream')}).status_code == 415


@pytest.mark.parametrize('extension,mime,video',[
    ('mp4','video/mp4',True),('mov','video/quicktime',True),('avi','video/x-msvideo',True),
    ('mp3','audio/mpeg',False),('wav','audio/wav',False),('m4a','audio/mp4',False),
])
def test_six_poc_formats_decode_and_return_reports(tmp_path,monkeypatch,extension,mime,video):
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        pytest.skip('FFmpeg and ffprobe required for real-format functional test')
    target=tmp_path/f'public-synthetic.{extension}'
    command=['ffmpeg','-nostdin','-v','error']
    if video: command += ['-f','lavfi','-i','testsrc2=size=64x64:rate=10']
    command += ['-f','lavfi','-i','sine=frequency=440:sample_rate=16000','-t','0.3']
    if video: command += ['-c:v','mpeg4','-c:a','pcm_s16le' if extension == 'avi' else 'aac']
    command.append(str(target))
    subprocess.run(command,check=True,capture_output=True)
    for name in ['aasist_command','scene_command','efficientnet_command','review_signals_command']:
        monkeypatch.setattr(settings,name,None)
    monkeypatch.setattr(settings,'auth_enabled',False)
    response=client.post('/v1/analyze',files={'file':(target.name,target.read_bytes(),mime)})
    assert response.status_code == 200
    report=response.json()
    assert report['media']['duration_seconds'] > 0
    assert report['media']['sha256']
    assert report['processing']['report_storage'] == 'saved'
    assert report['analysis_id']
    assert report['components'][0]['status'] == ('unavailable' if video else 'not_applicable')


def test_browser_can_send_delete() -> None:
    response = client.options(
        "/v1/reports/example",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "DELETE",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert response.status_code == 200
    assert "DELETE" in response.headers["access-control-allow-methods"]


def test_auth_config_enables_local_employee_login(monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "auth_mode", "employee")
    response = client.get("/v1/auth/config")
    assert response.status_code == 200
    assert response.json()["enabled"] is True
    assert response.json()["mode"] == "employee"


def test_analysis_requires_token_when_auth_enabled(monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_enabled", True)
    response = client.post("/v1/analyze", files={"file": ("synthetic.wav", synthetic_wav(), "audio/wav")})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_employee_login_issues_token_and_protects_analysis(monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "auth_mode", "employee")
    monkeypatch.setattr(settings, "employee_username", "dps.employee")
    monkeypatch.setattr(settings, "employee_password", "test-employee-password")
    monkeypatch.setattr(settings, "jwt_secret", "test-secret-that-is-long-enough-for-tests")
    denied = client.post("/v1/auth/login", json={"username": "dps.employee", "password": "wrong"})
    assert denied.status_code == 401
    login = client.post("/v1/auth/login", json={"username": "dps.employee", "password": "test-employee-password"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    response = client.post("/v1/analyze", headers={"Authorization": f"Bearer {token}"},
        files={"file": ("notes.txt", b"hello", "text/plain")})
    assert response.status_code == 415


def test_backend_does_not_serve_frontend():
    assert client.get("/").status_code == 404
    assert client.get("/login").status_code == 404


def test_frontend_cors_preflight():
    response = client.options("/v1/analyze", headers={
        "Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    denied = client.options("/v1/analyze", headers={
        "Origin": "https://untrusted.example",
        "Access-Control-Request-Method": "POST",
    })
    assert denied.status_code == 400
    assert "access-control-allow-origin" not in denied.headers


def test_audio_vertical_slice(monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_enabled", False)
    monkeypatch.setattr(settings, "aasist_command", None)
    response = client.post("/v1/analyze", files={"file": ("synthetic.wav", synthetic_wav(), "audio/wav")})
    assert response.status_code == 200
    report = response.json()
    assert report["advisory_only"] is True
    assert report["media"]["media_kind"] == "audio"
    assert report["media"]["duration_seconds"] == 0.1
    assert report["components"][0]["status"] == "not_applicable"
    assert report["components"][1]["status"] == "not_applicable"
    assert report["components"][2]["status"] == "unavailable"
    assert report["overall_synthetic_confidence"] is None
    assert "No applicable detector" in report["summary"]


def test_reports_are_persisted_and_reloaded(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(settings, "auth_enabled", False)
    monkeypatch.setattr(settings, "aasist_command", None)
    monkeypatch.setattr(settings, "report_db_path", tmp_path / "deeptrace.db")

    analyzed = client.post(
        "/v1/analyze",
        files={"file": ("persisted.wav", synthetic_wav(), "audio/wav")},
    )
    assert analyzed.status_code == 200
    report = analyzed.json()

    history = client.get("/v1/reports")
    assert history.status_code == 200
    assert history.json() == [{
        "report_id": report["report_id"],
        "generated_at": report["generated_at"],
        "filename": "persisted.wav",
        "media_kind": "audio",
        "overall_synthetic_confidence": None,
        "owner": "local-development",
        "workflow_status": "draft",
        "reviewer": None,
    }]

    restored = client.get(f"/v1/reports/{report['report_id']}")
    assert restored.status_code == 200
    assert restored.json() == report
    removed = client.delete(f"/v1/reports/{report['report_id']}")
    assert removed.status_code == 204
    assert client.get(f"/v1/reports/{report['report_id']}").status_code == 404
    assert client.get("/v1/reports").json() == []


def test_analyst_submits_report_to_supervisor(monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "auth_mode", "employee")
    monkeypatch.setattr(settings, "employee_username", "dps.employee")
    monkeypatch.setattr(settings, "employee_password", "analyst-pass")
    monkeypatch.setattr(settings, "supervisor_username", "dps.supervisor")
    monkeypatch.setattr(settings, "supervisor_password", "review-pass")
    monkeypatch.setattr(settings, "jwt_secret", "test-secret-that-is-long-enough-for-tests")
    monkeypatch.setattr(settings, "aasist_command", None)

    analyst_login = client.post(
        "/v1/auth/login", json={"username": "dps.employee", "password": "analyst-pass"},
    ).json()
    supervisor_login = client.post(
        "/v1/auth/login", json={"username": "dps.supervisor", "password": "review-pass"},
    ).json()
    assert analyst_login["role"] == "analyst"
    assert supervisor_login["role"] == "supervisor"
    analyst_headers = {"Authorization": f"Bearer {analyst_login['access_token']}"}
    supervisor_headers = {"Authorization": f"Bearer {supervisor_login['access_token']}"}

    analyzed = client.post(
        "/v1/analyze", headers=analyst_headers,
        files={"file": ("review.wav", synthetic_wav(), "audio/wav")},
    )
    report_id = analyzed.json()["report_id"]
    assert client.get("/v1/reports", headers=supervisor_headers).json() == []

    submitted = client.post(f"/v1/reports/{report_id}/submit", headers=analyst_headers)
    assert submitted.status_code == 200
    assert submitted.json() == {"status": "submitted", "reviewer": "dps.supervisor"}

    queue = client.get("/v1/reports", headers=supervisor_headers).json()
    assert queue[0]["report_id"] == report_id
    assert queue[0]["workflow_status"] == "submitted"
    assert queue[0]["owner"] == "dps.employee"
    assert client.get(f"/v1/reports/{report_id}", headers=supervisor_headers).status_code == 200
    media = client.get(f"/v1/reports/{report_id}/media", headers=supervisor_headers)
    assert media.status_code == 200
    assert media.content == synthetic_wav()

    denied_review = client.post(f"/v1/reports/{report_id}/review/start", headers=analyst_headers)
    assert denied_review.status_code == 403
    analyst_comment = client.post(
        f"/v1/reports/{report_id}/comments", headers=analyst_headers,
        json={"body": "Check the audio model coverage."},
    )
    assert analyst_comment.status_code == 200
    comments = client.get(f"/v1/reports/{report_id}/comments", headers=supervisor_headers)
    assert comments.json()[0]["author"] == "dps.employee"

    analyst_note = client.put(
        f"/v1/reports/{report_id}/notebook", headers=analyst_headers,
        json={"body": "Private analyst notes"},
    )
    assert analyst_note.status_code == 200
    supervisor_note = client.get(f"/v1/reports/{report_id}/notebook", headers=supervisor_headers)
    assert supervisor_note.json()["body"] == ""

    started = client.post(f"/v1/reports/{report_id}/review/start", headers=supervisor_headers)
    assert started.json() == {"status": "in_review"}
    completed = client.post(f"/v1/reports/{report_id}/review/complete", headers=supervisor_headers)
    assert completed.json() == {"status": "reviewed"}
    assert client.get(f"/v1/reports/{report_id}", headers=supervisor_headers).json()["workflow_status"] == "reviewed"

    profile = client.patch(
        "/v1/profile", headers=supervisor_headers,
        json={"display_name": "Taylor Reed", "title": "Review Lead"},
    )
    assert profile.json() == {
        "username": "dps.supervisor", "role": "supervisor",
        "display_name": "Taylor Reed", "title": "Review Lead",
    }


def test_rejects_unsupported_type(monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_enabled", False)
    response = client.post("/v1/analyze", files={"file": ("notes.txt", b"hello", "text/plain")})
    assert response.status_code == 415


@pytest.mark.parametrize(("content_type", "expected"), [
    ("video/mp4", "video"),
    ("video/quicktime", "video"),
    ("video/x-msvideo", "video"),
    ("video/avi", "video"),
    ("audio/mpeg", "audio"),
    ("audio/wav", "audio"),
    ("audio/x-wav", "audio"),
    ("audio/mp4", "audio"),
    ("audio/x-m4a", "audio"),
])
def test_classifies_scope_media_types(content_type, expected):
    from deeptrace.media import classify_media

    assert classify_media(content_type) == expected


def test_candidate_selection_and_report_documentation(monkeypatch):
    from deeptrace.analyzers.audio import AASISTAudioAnalyzer
    from deeptrace.schemas import ComponentResult
    monkeypatch.setattr(settings, 'auth_enabled', False)
    monkeypatch.setattr(settings, 'audio_model', 'aasist-l')
    monkeypatch.setattr(settings, 'scene_command', None)
    def infer(self, path, metadata):
        assert self.model_name == 'AASIST-L'
        assert path.exists()
        return ComponentResult(component='audio', status='functional', model_name=self.model_name,
            model_version='test', checkpoint='fixture-hash', synthetic_confidence=0.7)
    monkeypatch.setattr(AASISTAudioAnalyzer, 'analyze', infer)
    response = client.post('/v1/analyze', files={'file': ('synthetic.wav', synthetic_wav(), 'audio/wav')})
    report = response.json()
    assert response.status_code == 200
    assert report['components'][2]['model_name'] == 'AASIST-L'
    assert report['components'][0]['model_name'] == 'DeepfakeBench EfficientNet-B4'
    assert report['overall_synthetic_confidence'] is None
    assert report['report_version'] == '0.3'
    assert len(report['integrity']['received_file_hash']) == 64
    assert report['references'] and report['methods'] and report['limitations']


def test_video_returns_three_independent_detectors_without_weighted_report(monkeypatch, tmp_path):
    from deeptrace import api
    from deeptrace.analyzers.audio import AASISTAudioAnalyzer
    from deeptrace.analyzers.video import EfficientNetVideoAnalyzer
    from deeptrace.schemas import ComponentResult

    frames = tmp_path / "prepared" / "frames"
    frames.mkdir(parents=True)
    (frames / "frame_000001.jpg").write_bytes(b"frame")
    audio = tmp_path / "prepared" / "audio.wav"
    audio.write_bytes(synthetic_wav())

    def prepare(*_args, **_kwargs):
        return frames, audio

    def video_infer(self, path, metadata):
        assert path == frames and metadata.media_kind == "video"
        return ComponentResult(component="video", status="functional", model_name=self.model_name,
            model_version="test-video", synthetic_confidence=0.8)

    def audio_infer(self, path, metadata):
        assert path == audio and metadata.media_kind == "video"
        return ComponentResult(component="audio", status="functional", model_name=self.model_name,
            model_version="test-audio", synthetic_confidence=0.2)

    monkeypatch.setattr(settings, "auth_enabled", False)
    monkeypatch.setattr(api, "prepare_video", prepare)
    monkeypatch.setattr(api, "cleanup_prepared", lambda _path: None)
    monkeypatch.setattr(EfficientNetVideoAnalyzer, "analyze", video_infer)
    monkeypatch.setattr(AASISTAudioAnalyzer, "analyze", audio_infer)
    monkeypatch.setattr(settings, "video_model", "efficientnetb4")
    monkeypatch.setattr(settings, "audio_model", "aasist")
    monkeypatch.setattr(settings, "visual_weight", 0.75)
    monkeypatch.setattr(settings, "scene_command", None)

    response = client.post("/v1/analyze", files={"file": ("clip.mp4", b"video", "video/mp4")})
    assert response.status_code == 200
    report = response.json()
    assert [component["status"] for component in report["components"]] == ["functional", "unavailable", "functional"]
    assert report["overall_synthetic_confidence"] is None
    assert [item["model_score"] for item in report["evidence_summary"]] == [0.8, None, 0.2]
    assert "independent" in report["summary"]

    from deeptrace.analyzers.video import SceneVideoAnalyzer

    def scene_infer(self, path, metadata):
        assert path == frames
        return ComponentResult(component="video", status="functional", model_name=self.model_name,
            model_version="test-scene", synthetic_confidence=0.96)

    monkeypatch.setattr(SceneVideoAnalyzer, "analyze", scene_infer)
    monkeypatch.setattr(settings, "scene_command", "scene {frames_dir}")
    report = client.post("/v1/analyze", files={"file": ("clip.mp4", b"video", "video/mp4")}).json()
    assert report["components"][0]["synthetic_confidence"] == 0.8
    assert report["components"][1]["synthetic_confidence"] == 0.96
    assert report["components"][1]["model_name"].endswith("Community Forensics ViT-S/384 (frontier fine-tune)")
    assert report["overall_synthetic_confidence"] is None
