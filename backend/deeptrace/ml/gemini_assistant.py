"""Gemini case assistant. Amazon Bedrock can replace this provider later."""

import json
import logging
import mimetypes
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from deeptrace.ml.assistant import REFUSAL, RulesCaseAssistant

logger = logging.getLogger("deeptrace.assistant")

SYSTEM = (
    "You are DeepTrace's case assistant for one analysis. You may be given the recording itself. "
    "Model outputs are advisory screening signals, not proof. "
    "Never say the media is confirmed authentic, fake, or a deepfake. "
    "Cite finding IDs and timestamps when you discuss automated findings. "
    "Keep model findings separate from investigator dispositions. "
    "Do not invent findings that are absent from the supplied list. "
    "The video detector scores aligned face crops only. Fully generated video is not the same as a face-swap deepfake. "
    "If you notice something in the recording that no finding covers, describe it as an observation of the file, not a forensic conclusion. "
    f"{REFUSAL}"
)
MAX_MEDIA_BYTES = 80 * 1024 * 1024


class GeminiCaseAssistant:
    """Sends the question, case record, and media file to Gemini when a key is configured."""

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
        self.fallback = RulesCaseAssistant()

    def answer(self, question: str, context: dict) -> dict:
        try:
            text, attached = self._generate(question, context)
        except (OSError, HTTPError, URLError, TimeoutError, json.JSONDecodeError, KeyError, ValueError) as exc:
            logger.info("gemini_unavailable %s", type(exc).__name__)
            fallback = self.fallback.answer(question, context)
            fallback["answer"] += " The media model was unavailable, so this answer uses the case record only."
            return fallback
        return {
            "answer": text,
            "citations": _citations(text, context.get("findings") or []),
            "advisory_only": True,
            "provider": "gemini" if attached else "gemini-without-media",
        }

    def _generate(self, question: str, context: dict) -> tuple[str, bool]:
        file_uri, mime = _upload_media(self.api_key, context.get("media_path"), context.get("content_type"))
        parts: list[dict] = []
        if file_uri and mime:
            parts.append({"file_data": {"mime_type": mime, "file_uri": file_uri}})
        parts.append({"text": _prompt(question, context, attached=bool(file_uri))})
        contents = [{"role": "user" if turn["role"] == "user" else "model", "parts": [{"text": turn["text"]}]} for turn in context.get("history") or []]
        contents.append({"role": "user", "parts": parts})
        payload = json.dumps({
            "system_instruction": {"parts": [{"text": SYSTEM}]},
            "contents": contents,
        }).encode()
        request = Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}",
            data=payload, headers={"Content-Type": "application/json"}, method="POST",
        )
        with urlopen(request, timeout=120) as response:
            body = json.load(response)
        text = body["candidates"][0]["content"]["parts"][0]["text"].strip()
        if not text:
            raise ValueError("empty Gemini response")
        return text, bool(file_uri)


def _prompt(question: str, context: dict, *, attached: bool) -> str:
    findings = context.get("findings") or []
    lines = ["Automated findings (model outputs, not investigator conclusions):"]
    if findings:
        for item in findings:
            end = item.get("end_time")
            span = f"{item['start_time']:.1f}s" if end is None else f"{item['start_time']:.1f}s–{end:.1f}s"
            lines.append(
                f"- Finding {item['id']} {item['modality']} {span} model score {item['raw_score']:.2f} "
                f"disposition {item.get('human_disposition') or 'not reviewed'}"
            )
    else:
        lines.append("- None exceeded the decision threshold.")
    if context.get("report_excerpt"):
        lines.append("AI-generated report excerpt:\n" + context["report_excerpt"])
    lines.append("The recording is attached." if attached else "The recording was not attached. Answer from the case record only.")
    lines.append("Question: " + question.strip())
    return "\n".join(lines)


def _upload_media(api_key: str, path: str | None, content_type: str | None) -> tuple[str | None, str | None]:
    if not path:
        return None, None
    media = Path(path)
    if not media.is_file() or media.stat().st_size > MAX_MEDIA_BYTES:
        return None, None
    mime = content_type if content_type and content_type != "application/octet-stream" else mimetypes.guess_type(media.name)[0]
    if not mime or not (mime.startswith("video/") or mime.startswith("audio/")):
        return None, None
    start = Request(
        f"https://generativelanguage.googleapis.com/upload/v1beta/files?key={api_key}",
        data=json.dumps({"file": {"display_name": "analysis-media"}}).encode(),
        headers={
            "Content-Type": "application/json",
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(media.stat().st_size),
            "X-Goog-Upload-Header-Content-Type": mime,
        },
        method="POST",
    )
    with urlopen(start, timeout=30) as response:
        upload_url = response.headers["X-Goog-Upload-URL"]
    upload = Request(
        upload_url, data=media.read_bytes(),
        headers={"Content-Length": str(media.stat().st_size), "X-Goog-Upload-Offset": "0", "X-Goog-Upload-Command": "upload, finalize"},
        method="POST",
    )
    with urlopen(upload, timeout=120) as response:
        uploaded = json.load(response)
    file_uri = uploaded["file"]["uri"]
    return file_uri, mime


def _citations(answer: str, findings: list[dict]) -> list[dict]:
    return [
        {"finding_id": item["id"], "start_time": item["start_time"]}
        for item in findings if item["id"] in answer
    ]
