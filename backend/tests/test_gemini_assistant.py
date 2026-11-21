import json
from urllib.error import URLError

from deeptrace.ml.gemini_assistant import SYSTEM, GeminiCaseAssistant, _prompt


def test_prompt_keeps_model_findings_separate_from_proof():
    text = _prompt("What is in this video?", {
        "findings": [{
            "id": "finding-1", "modality": "video", "start_time": 1.0, "end_time": 2.0,
            "raw_score": 0.81, "human_disposition": None,
        }],
    }, attached=True)
    assert "Finding finding-1" in text
    assert "The recording is attached." in text
    assert "Never say" in SYSTEM
    assert "confirmed authentic" in SYSTEM


def test_gemini_sends_the_recording_and_cites_a_named_finding(tmp_path, monkeypatch):
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"not-a-real-video")

    def fake_urlopen(request, timeout=0):
        url = request.full_url
        command = request.get_header("X-goog-upload-command")
        if "upload/v1beta/files" in url and command == "start":
            return _Response(b"{}", {"X-Goog-Upload-URL": "https://upload.example/session"})
        if url.startswith("https://upload.example"):
            return _Response(json.dumps({"file": {"uri": "files/case-media"}}).encode())
        body = json.loads(request.data.decode())
        assert body["contents"][-1]["parts"][0]["file_data"]["file_uri"] == "files/case-media"
        return _Response(json.dumps({
            "candidates": [{"content": {"parts": [{"text": "Finding finding-1 is a screening signal, not proof."}]}}],
        }).encode())

    monkeypatch.setattr("deeptrace.ml.gemini_assistant.urlopen", fake_urlopen)
    result = GeminiCaseAssistant("test-key", "gemini-2.5-flash").answer("What do you see?", {
        "findings": [{
            "id": "finding-1", "modality": "video", "start_time": 0.0, "end_time": 1.0,
            "raw_score": 0.9, "human_disposition": None,
        }],
        "media_path": str(media),
        "content_type": "video/mp4",
        "history": [{"role": "user", "text": "Earlier question"}, {"role": "assistant", "text": "Earlier answer"}],
    })
    assert result["provider"] == "gemini"
    assert result["advisory_only"] is True
    assert result["citations"] == [{"finding_id": "finding-1", "start_time": 0.0}]


def test_gemini_falls_back_to_the_case_record_when_the_model_is_unavailable(monkeypatch):
    def fail(request, timeout=0):
        raise URLError("offline")

    monkeypatch.setattr("deeptrace.ml.gemini_assistant.urlopen", fail)
    result = GeminiCaseAssistant("test-key", "gemini-2.5-flash").answer("Is this fake?", {"findings": [], "history": []})
    assert result["provider"] == "rules"
    assert "cannot establish" in result["answer"]
    assert "case record only" in result["answer"]


class _Response:
    def __init__(self, payload: bytes, headers: dict | None = None):
        self.payload = payload
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.payload
