import io
import wave

import pytest
from fastapi.testclient import TestClient

from deeptrace.config import settings
from deeptrace.main import app
from deeptrace.ml.attribution import grad_cam
from deeptrace.ml.evaluation import auc, brier_score, confusion, equal_error_rate, fit_temperature

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "report_db_path", tmp_path / "deeptrace.db")
    monkeypatch.setattr(settings, "report_media_dir", tmp_path / "media")
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'workflow.db'}")
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "auth_mode", "employee")
    monkeypatch.setattr(settings, "employee_username", "dps.employee")
    monkeypatch.setattr(settings, "employee_password", "analyst-pass")
    monkeypatch.setattr(settings, "supervisor_username", "dps.supervisor")
    monkeypatch.setattr(settings, "supervisor_password", "review-pass")
    monkeypatch.setattr(settings, "reviewer_username", "dps.reviewer")
    monkeypatch.setattr(settings, "reviewer_password", "expert-pass")
    monkeypatch.setattr(settings, "admin_username", "dps.admin")
    monkeypatch.setattr(settings, "admin_password", "admin-pass")
    monkeypatch.setattr(settings, "jwt_secret", "test-secret-that-is-long-enough-for-tests")
    monkeypatch.setattr(settings, "aasist_command", None)
    from deeptrace.db.session import reset_engine
    reset_engine()


def wav() -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\x00\x00" * 800)
    return output.getvalue()


def login(username: str, password: str) -> dict:
    response = client.post("/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def analyze(headers: dict) -> dict:
    response = client.post("/v1/analyze", headers=headers, files={"file": ("clip.wav", wav(), "audio/wav")})
    assert response.status_code == 200
    return response.json()


def test_screening_opens_an_analysis_without_calling_the_score_a_probability():
    headers = login("dps.employee", "analyst-pass")
    report = analyze(headers)
    detail = client.get(f"/v1/analyses/{report['analysis_id']}", headers=headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["status"] == "AI_SCREENING_COMPLETE"
    assert body["limitation"].startswith("DeepTrace provides automated screening assistance.")
    assert body["model_runs"][0]["calibrated_probability"] is None
    assert "probability" not in body["model_runs"][0]["model_name"].lower()


def test_dispositions_are_append_only_and_hidden_from_other_investigators(monkeypatch):
    from deeptrace.analyzers.audio import AASISTAudioAnalyzer
    from deeptrace.schemas import ComponentResult, ModelSample

    def infer(self, path, metadata):
        return ComponentResult(
            component="audio", status="functional", model_name=self.model_name, model_version="test",
            synthetic_confidence=0.81, samples=[ModelSample(
                start_time=1.2, end_time=2.4, raw_score=0.81, predicted_class="possible_manipulation", score_scope="file",
            )],
        )

    monkeypatch.setattr(AASISTAudioAnalyzer, "analyze", infer)
    analyst = login("dps.employee", "analyst-pass")
    reviewer = login("dps.reviewer", "expert-pass")
    other = login("dps.supervisor", "review-pass")
    report = analyze(analyst)
    analysis_id = report["analysis_id"]
    assert client.get(f"/v1/analyses/{analysis_id}", headers=reviewer).status_code == 404
    finding_id = client.get(f"/v1/analyses/{analysis_id}", headers=analyst).json()["findings"][0]["id"]
    first = client.post(
        f"/v1/analyses/{analysis_id}/findings/{finding_id}/reviews", headers=analyst,
        json={"disposition": "uncertain", "comment": "Compression may explain this."},
    )
    assert first.status_code == 200
    second = client.post(
        f"/v1/analyses/{analysis_id}/findings/{finding_id}/reviews", headers=analyst,
        json={"disposition": "needs_expert_review", "comment": "Please review the segment."},
    )
    assert second.status_code == 200
    reviews = second.json()["reviews"]
    assert reviews[0]["previous_value"] is None
    assert reviews[1]["previous_value"] == "uncertain"
    assert reviews[1]["new_value"] == "needs_expert_review"
    escalated = client.get(f"/v1/analyses/{analysis_id}", headers=reviewer)
    assert escalated.status_code == 200
    assert escalated.json()["status"] == "EXPERT_REVIEW_REQUESTED"
    denied = client.post(f"/v1/analyses/{analysis_id}/report/finalize", headers=analyst)
    assert denied.status_code == 403
    assert client.get(f"/v1/analyses/{analysis_id}", headers=other).status_code == 200


def test_report_edits_keep_the_ai_original():
    analyst = login("dps.employee", "analyst-pass")
    supervisor = login("dps.supervisor", "review-pass")
    analysis_id = analyze(analyst)["analysis_id"]
    current = client.get(f"/v1/analyses/{analysis_id}/report", headers=analyst).json()
    original = current["ai_original"]["investigator_assessment"]["text"]
    sections = current["current"]
    sections["investigator_assessment"] = {"text": "I do not treat the score as proof.", "origin": "human"}
    saved = client.put(f"/v1/analyses/{analysis_id}/report", headers=analyst, json={"sections": sections})
    assert saved.status_code == 200
    body = saved.json()
    assert body["ai_original"]["investigator_assessment"]["text"] == original
    assert body["current"]["investigator_assessment"]["origin"] == "human"
    diff = client.get(f"/v1/analyses/{analysis_id}/report/diff", headers=analyst).json()
    assessment = next(item for item in diff if item["section"] == "investigator_assessment")
    assert assessment["changed"] is True
    submitted = client.post(f"/v1/analyses/{analysis_id}/report/submit", headers=analyst)
    assert submitted.json()["status"] == "SUPERVISOR_REVIEW"
    finalized = client.post(f"/v1/analyses/{analysis_id}/report/finalize", headers=supervisor)
    assert finalized.status_code == 200
    assert finalized.json()["status"] == "FINALIZED"
    locked = client.put(f"/v1/analyses/{analysis_id}/report", headers=analyst, json={"sections": sections})
    assert locked.status_code == 409


def test_assistant_cites_findings_and_does_not_declare_a_deepfake(monkeypatch):
    from deeptrace.analyzers.audio import AASISTAudioAnalyzer
    from deeptrace.schemas import ComponentResult, ModelSample

    def infer(self, path, metadata):
        return ComponentResult(
            component="audio", status="functional", model_name="AASIST", model_version="test",
            synthetic_confidence=0.77, samples=[ModelSample(
                start_time=0, end_time=1, raw_score=0.77, predicted_class="possible_manipulation",
            )],
        )

    monkeypatch.setattr(AASISTAudioAnalyzer, "analyze", infer)
    headers = login("dps.employee", "analyst-pass")
    analysis_id = analyze(headers)["analysis_id"]
    answer = client.post(
        f"/v1/analyses/{analysis_id}/assistant", headers=headers,
        json={"question": "Summarize the AI findings."},
    ).json()
    assert answer["citations"]
    assert "possible manipulation signal" in answer["answer"]
    assert "Deepfake confirmed" not in answer["answer"]
    refused = client.post(
        f"/v1/analyses/{analysis_id}/assistant", headers=headers,
        json={"question": "Is this fake?"},
    ).json()
    assert "cannot establish" in refused["answer"]


def test_admin_creates_a_directory_user_and_audit_is_not_writable():
    admin = login("dps.admin", "admin-pass")
    created = client.post("/v1/users", headers=admin, json={
        "username": "case.officer", "password": "long-enough", "role": "investigator", "display_name": "Case Officer",
    })
    assert created.status_code == 200
    denied = client.get("/v1/users", headers=login("dps.employee", "analyst-pass"))
    assert denied.status_code == 403
    officer = login("case.officer", "long-enough")
    assert client.get("/v1/dashboard", headers=officer).status_code == 200
    audit = client.get("/v1/audit", headers=admin)
    assert audit.status_code == 200
    assert client.put("/v1/audit", headers=admin, json={"action": "delete"}).status_code == 405


def test_gradcam_and_auc_are_computable_without_being_applied_as_confidence():
    heatmap = grad_cam([[[0, 1], [0, 0]], [[1, 0], [0, 0]]], [[[0, 1], [0, 0]], [[0, 0], [0, 0]]])
    assert heatmap[0][1] == 1
    assert auc([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9]) == 1
    assert confusion([1, 0], [0.2, 0.9], 0.5) == {"tp": 0, "fp": 1, "tn": 0, "fn": 1}
    assert equal_error_rate([0, 1], [0.1, 0.9]) == 0
    assert brier_score([1, 0], [1, 0]) == 0
    fitted = fit_temperature([2, -2], [1, 0], dataset_version="fixture", preprocessing_version="v1")
    assert fitted.temperature > 0
    assert fitted.apply(0) == 0.5


def test_report_groups_window_findings_without_internal_ids():
    from types import SimpleNamespace

    from deeptrace.workflow.service import _finding_runs, _numbers

    def finding(start: float, model: str, score: float):
        return SimpleNamespace(
            id=f"uuid-{model}-{start}", start_time=start, end_time=start + 1, modality="video",
            model_name=model, raw_score=score, threshold=0.5,
        )

    scene = [finding(float(second), "Community Forensics ViT-S/384", 0.99) for second in range(10)]
    runs = _finding_runs([*scene, finding(9.0, "DeepfakeBench EfficientNet-B4", 0.55)])
    assert [(run["model"], run["numbers"], run["start"], run["end"]) for run in runs] == [
        ("Community Forensics ViT-S/384", list(range(1, 11)), 0.0, 10.0),
        ("DeepfakeBench EfficientNet-B4", [11], 9.0, 10.0),
    ]
    assert _numbers([1, 2, 3, 4, 6]) == "Findings 1–4, 6"
    assert _numbers([1, 2, 3]) == "Findings 1–3"
    assert _numbers([10]) == "Finding 10"


def test_model_settings_include_all_three_detectors_and_selected_commands(monkeypatch):
    headers = login('dps.employee', 'analyst-pass')
    monkeypatch.setattr(settings, 'video_model', 'efficientnetb4')
    monkeypatch.setattr(settings, 'efficientnet_command', None)
    monkeypatch.setattr(settings, 'effort_command', 'other-face-command')
    monkeypatch.setattr(settings, 'audio_model', 'aasist')
    monkeypatch.setattr(settings, 'aasist_command', None)
    monkeypatch.setattr(settings, 'nes2net_command', 'other-audio-command')
    monkeypatch.setattr(settings, 'scene_command', 'whole-frame-command')
    response = client.get('/v1/settings/models', headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body['scene_model'] == 'community_forensics'
    assert body['scene_configured'] is True
    assert body['video_configured'] is False
    assert body['audio_configured'] is False
    assert body['calibration_version'] is None
    monkeypatch.setattr(settings, 'video_model', 'effort')
    monkeypatch.setattr(settings, 'audio_model', 'nes2net')
    monkeypatch.setattr(settings, 'scene_command', None)
    body = client.get('/v1/settings/models', headers=headers).json()
    assert body['video_configured'] is True
    assert body['audio_configured'] is True
    assert body['scene_configured'] is False
