"""Amazon Bedrock case assistant.

Two models with separate jobs:

- The video model (Amazon Nova Lite by default) watches the recording and writes
  observations: once as a cached timeline, and on demand for a narrow follow-up.
  It never judges authenticity.
- The answer model (Claude Haiku 4.5 by default) answers the investigator. It never
  sees the recording; it reads the case record and the video model's observations,
  and may call ``inspect_video`` when the timeline lacks detail.

The workflow service persists the timeline; this module only talks to Bedrock.
"""

import json
import logging
import mimetypes
import re
from pathlib import Path
from typing import Any, Protocol

from deeptrace.ml.assistant import RulesCaseAssistant
from deeptrace.ml.gemini_assistant import SYSTEM as CASE_RULES
from deeptrace.ml.gemini_assistant import _case_record, _citations

logger = logging.getLogger("deeptrace.assistant")

TIMELINE_PROMPT_VERSION = "timeline-v1"
MAX_INLINE_VIDEO_BYTES = 20 * 1024 * 1024
MAX_TOOL_CALLS = 3
MAX_INSPECT_SECONDS = 60.0
VIDEO_FORMATS = {
    ".mp4": "mp4", ".m4v": "mp4", ".mov": "mov", ".mkv": "mkv", ".webm": "webm", ".flv": "flv",
    ".mpeg": "mpeg", ".mpg": "mpg", ".wmv": "wmv", ".3gp": "three_gp",
}

OBSERVER_SYSTEM = (
    "You describe what is visible in a video for an investigator's case file. "
    "Describe only what can be seen: setting, people visible, actions, on-screen text, camera movement, cuts or edits, "
    "lighting and quality changes. Use timestamps in seconds from the start of the file. "
    "Do not judge whether the video is real, fake, manipulated, AI-generated, or a deepfake. "
    "Do not identify people by name. Say when something is unclear. You cannot hear audio; do not describe speech content."
)

TIMELINE_INSTRUCTION = (
    "Write a timeline of this video as JSON only, with no prose before or after. Schema: "
    '{"segments": [{"start": <seconds>, "end": <seconds>, "scene": <string>, "people_visible": <integer or null>, '
    '"on_screen_text": [<string>], "camera": <string>, "notable": <string>}], "limitations": [<string>]}. '
    "Use segments of roughly 10 seconds, or shorter where the scene changes."
)

ANSWER_SYSTEM = (
    f"{CASE_RULES} "
    "You do not see the recording yourself. You may receive a timeline written by a separate video model. "
    "Those are observations of the file, not detector findings and not forensic conclusions; say so when you rely on them. "
    "The video model cannot hear audio. "
    "When the timeline lacks the detail a question needs, call inspect_video with a short time range and a specific question. "
    "If you still cannot tell, say so."
)

INSPECT_TOOL = {"toolSpec": {
    "name": "inspect_video",
    "description": (
        "Ask the video model to look closely at a time range of the recording and describe what is visible. "
        "Returns observations only, never an authenticity judgment."
    ),
    "inputSchema": {"json": {
        "type": "object",
        "properties": {
            "start_s": {"type": "number", "description": "Start of the range, seconds from the start of the file."},
            "end_s": {"type": "number", "description": "End of the range, seconds from the start of the file."},
            "question": {"type": "string", "description": "What to look for in that range."},
        },
        "required": ["start_s", "end_s", "question"],
    }},
}}


class BedrockClient(Protocol):
    def converse(self, **kwargs: Any) -> dict: ...


def bedrock_client(region: str | None) -> BedrockClient:
    import boto3
    return boto3.client("bedrock-runtime", region_name=region) if region else boto3.client("bedrock-runtime")


def video_block(path: str | None, content_type: str | None, s3_uri: str | None = None) -> dict | None:
    """Converse ``video`` content block, or None when it cannot be sent.

    Files up to 20 MB go inline. Larger files are sent by S3 reference when the recording is stored in S3
    (the bucket must be in the Bedrock region and readable by the caller's role).
    """
    if not path:
        return None
    media = Path(path)
    mime = content_type if content_type and content_type != "application/octet-stream" else mimetypes.guess_type(media.name)[0]
    video_format = VIDEO_FORMATS.get(media.suffix.lower())
    if not video_format or not mime or not mime.startswith("video/"):
        return None
    if media.is_file() and media.stat().st_size <= MAX_INLINE_VIDEO_BYTES:
        return {"video": {"format": video_format, "source": {"bytes": media.read_bytes()}}}
    if s3_uri:
        return {"video": {"format": video_format, "source": {"s3Location": {"uri": s3_uri}}}}
    return None


class NovaVideoObserver:
    """Turns a recording into written observations. Raises on Bedrock errors; callers decide the fallback."""

    def __init__(self, client: BedrockClient, model_id: str):
        self.client = client
        self.model_id = model_id

    def timeline(self, video: dict) -> dict:
        text = self._ask(video, TIMELINE_INSTRUCTION, max_tokens=4000)
        return parse_timeline(text)

    def inspect(self, video: dict, start_s: float, end_s: float, question: str) -> str:
        start_s = max(0.0, float(start_s))
        end_s = max(start_s, min(float(end_s), start_s + MAX_INSPECT_SECONDS))
        instruction = (
            f"Look only at {start_s:.1f}s to {end_s:.1f}s of this video. {question.strip()} "
            "Describe what is visible with timestamps. If it cannot be determined from the picture, say so."
        )
        return self._ask(video, instruction, max_tokens=800)

    def _ask(self, video: dict, instruction: str, *, max_tokens: int) -> str:
        response = self.client.converse(
            modelId=self.model_id,
            system=[{"text": OBSERVER_SYSTEM}],
            messages=[{"role": "user", "content": [video, {"text": instruction}]}],
            inferenceConfig={"maxTokens": max_tokens, "temperature": 0.1},
        )
        text = _text_of(response["output"]["message"]).strip()
        if not text:
            raise ValueError("empty video model response")
        return text


class BedrockCaseAssistant:
    """Answers with the answer model, using cached observations and an optional inspect_video tool."""

    def __init__(self, client: BedrockClient, answer_model: str, observer: NovaVideoObserver | None = None,
                 max_tool_calls: int = MAX_TOOL_CALLS):
        self.client = client
        self.answer_model = answer_model
        self.observer = observer
        self.max_tool_calls = max_tool_calls
        self.fallback = RulesCaseAssistant()

    def answer(self, question: str, context: dict) -> dict:
        video = context.get("video")
        observations = context.get("observations")
        try:
            text, inspected = self._generate(question, context, video if self.observer else None)
        except Exception as exc:  # boto3 raises botocore errors that are not importable without boto3
            logger.info("bedrock_unavailable %s", type(exc).__name__)
            fallback = self.fallback.answer(question, context)
            fallback["answer"] += " The language model was unavailable, so this answer uses the case record only."
            return fallback
        provider = "bedrock" if observations or inspected else "bedrock-without-media"
        return {
            "answer": text,
            "citations": _citations(text, context.get("findings") or []),
            "advisory_only": True,
            "provider": provider,
        }

    def _generate(self, question: str, context: dict, video: dict | None) -> tuple[str, bool]:
        messages = _history(context.get("history") or [])
        messages.append({"role": "user", "content": [{"text": _prompt(question, context, can_inspect=video is not None)}]})
        request: dict[str, Any] = {
            "modelId": self.answer_model,
            "system": [{"text": ANSWER_SYSTEM}],
            "inferenceConfig": {"maxTokens": 1200, "temperature": 0.2},
        }
        if video is not None:
            request["toolConfig"] = {"tools": [INSPECT_TOOL]}
        inspected = False
        rounds = 0
        while True:
            response = self.client.converse(messages=messages, **request)
            message = response["output"]["message"]
            calls = [block["toolUse"] for block in message.get("content", []) if "toolUse" in block]
            if response.get("stopReason") != "tool_use" or not calls or "toolConfig" not in request:
                text = _text_of(message).strip()
                if not text:
                    raise ValueError("empty answer model response")
                return text, inspected
            messages.append(message)
            messages.append({"role": "user", "content": [{"toolResult": self._run_tool(call, video)} for call in calls]})
            inspected = True
            rounds += 1
            if rounds >= self.max_tool_calls:
                # Budget spent: Converse rejects tool blocks without toolConfig, so fold them into text.
                request.pop("toolConfig")
                messages = _strip_tool_blocks(messages)

    def _run_tool(self, call: dict, video: dict | None) -> dict:
        tool_id = call["toolUseId"]
        if call.get("name") != "inspect_video" or video is None or self.observer is None:
            return {"toolUseId": tool_id, "status": "error", "content": [{"text": "The recording is not available."}]}
        args = call.get("input") or {}
        try:
            text = self.observer.inspect(video, args.get("start_s", 0), args.get("end_s", 0), str(args.get("question", "")))
        except Exception as exc:
            logger.info("bedrock_inspect_failed %s", type(exc).__name__)
            return {"toolUseId": tool_id, "status": "error", "content": [{"text": "The video model was unavailable."}]}
        return {"toolUseId": tool_id, "content": [{"text": "Video model observations (not findings): " + text}]}


def parse_timeline(text: str) -> dict:
    """Parse the video model's JSON timeline; keep the raw text when it is not valid JSON."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict) and isinstance(data.get("segments"), list):
            segments = [item for item in data["segments"] if isinstance(item, dict)]
            limitations = [str(item) for item in data.get("limitations") or [] if item]
            return {"segments": segments, "limitations": limitations}
    return {"segments": [], "limitations": [], "text": text.strip()}


def _prompt(question: str, context: dict, *, can_inspect: bool) -> str:
    lines = _case_record(context)
    observations = context.get("observations")
    if observations:
        lines.append(
            "Video model observations (descriptions of the file, not findings or forensic conclusions):\n"
            + json.dumps(observations, ensure_ascii=False)
        )
    elif can_inspect:
        lines.append("No timeline is stored for this recording. Use inspect_video if the question is about what it shows.")
    else:
        lines.append("The recording cannot be viewed for this question. Answer from the case record only.")
    lines.append("Question: " + question.strip())
    return "\n".join(lines)


def _history(turns: list[dict]) -> list[dict]:
    """Converse needs alternating roles that start with the user; merge or drop turns that break that."""
    messages: list[dict] = []
    for turn in turns:
        role = "user" if turn.get("role") == "user" else "assistant"
        text = str(turn.get("text") or "").strip()
        if not text or (not messages and role == "assistant"):
            continue
        if messages and messages[-1]["role"] == role:
            messages[-1]["content"][0]["text"] += "\n" + text
        else:
            messages.append({"role": role, "content": [{"text": text}]})
    if messages and messages[-1]["role"] == "user":
        messages.append({"role": "assistant", "content": [{"text": "(no answer recorded)"}]})
    return messages


def _strip_tool_blocks(messages: list[dict]) -> list[dict]:
    """Once the tool budget is spent, fold tool traffic into text so the model must answer without tools."""
    cleaned: list[dict] = []
    for message in messages:
        parts = []
        for block in message.get("content", []):
            if "text" in block:
                parts.append(block["text"])
            elif "toolUse" in block:
                parts.append(f"(asked the video model: {json.dumps(block['toolUse'].get('input') or {})})")
            elif "toolResult" in block:
                parts.extend(item.get("text", "") for item in block["toolResult"].get("content", []))
        text = "\n".join(part for part in parts if part)
        if cleaned and cleaned[-1]["role"] == message["role"]:
            cleaned[-1]["content"][0]["text"] += "\n" + text
        elif text:
            cleaned.append({"role": message["role"], "content": [{"text": text}]})
    note = "Answer the question now without further tools."
    if cleaned and cleaned[-1]["role"] == "user":
        cleaned[-1]["content"][0]["text"] += "\n" + note
    else:
        cleaned.append({"role": "user", "content": [{"text": note}]})
    return cleaned


def _text_of(message: dict) -> str:
    return "\n".join(block["text"] for block in message.get("content", []) if "text" in block)
