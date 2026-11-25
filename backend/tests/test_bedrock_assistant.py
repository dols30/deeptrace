import json

from deeptrace.ml.bedrock_assistant import (
    ANSWER_SYSTEM, OBSERVER_SYSTEM, BedrockCaseAssistant, NovaVideoObserver, parse_timeline, video_block,
)

FINDING = {
    "id": "finding-1", "modality": "video", "start_time": 2.0, "end_time": 3.0,
    "raw_score": 0.81, "human_disposition": None,
}
VIDEO = {"video": {"format": "mp4", "source": {"bytes": b"clip"}}}


class FakeBedrock:
    """Scripted Converse responses keyed by model ID; records every request."""

    def __init__(self, scripts: dict[str, list]):
        self.scripts = {key: list(value) for key, value in scripts.items()}
        self.calls: list[dict] = []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        reply = self.scripts[kwargs["modelId"]].pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def text(value: str) -> dict:
    return {"output": {"message": {"role": "assistant", "content": [{"text": value}]}}, "stopReason": "end_turn"}


def tool_use(tool_id: str, start: float, end: float, question: str) -> dict:
    return {"output": {"message": {"role": "assistant", "content": [{"toolUse": {
        "toolUseId": tool_id, "name": "inspect_video", "input": {"start_s": start, "end_s": end, "question": question},
    }}]}}, "stopReason": "tool_use"}


def test_prompts_keep_observations_separate_from_findings_and_proof():
    assert "Do not judge whether the video is real" in OBSERVER_SYSTEM
    assert "Never say" in ANSWER_SYSTEM
    assert "not detector findings" in ANSWER_SYSTEM


def test_timeline_is_parsed_from_json_and_falls_back_to_text():
    parsed = parse_timeline('Here: {"segments": [{"start": 0, "end": 10, "scene": "office"}], "limitations": ["dark"]}')
    assert parsed == {"segments": [{"start": 0, "end": 10, "scene": "office"}], "limitations": ["dark"]}
    raw = parse_timeline("A person sits at a desk.")
    assert raw["segments"] == [] and raw["text"] == "A person sits at a desk."


def test_video_block_sends_supported_video_and_skips_audio_or_large_files(tmp_path, monkeypatch):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"clip")
    assert video_block(str(clip), "video/mp4") == {"video": {"format": "mp4", "source": {"bytes": b"clip"}}}
    audio = tmp_path / "voice.wav"
    audio.write_bytes(b"wav")
    assert video_block(str(audio), "audio/wav") is None
    monkeypatch.setattr("deeptrace.ml.bedrock_assistant.MAX_INLINE_VIDEO_BYTES", 2)
    assert video_block(str(clip), "video/mp4") is None
    uri = "s3://case-media/deeptrace/media/r/clip.mp4"
    assert video_block(str(clip), "video/mp4", uri) == {"video": {"format": "mp4", "source": {"s3Location": {"uri": uri}}}}


def test_observer_writes_a_timeline_with_the_video_model():
    client = FakeBedrock({"nova": [text('{"segments": [{"start": 0, "end": 5, "scene": "street"}]}')]})
    timeline = NovaVideoObserver(client, "nova").timeline(VIDEO)
    assert timeline["segments"][0]["scene"] == "street"
    sent = client.calls[0]["messages"][0]["content"]
    assert sent[0] == VIDEO and "JSON" in sent[1]["text"]


def test_answer_uses_cached_observations_and_cites_findings():
    client = FakeBedrock({"haiku": [text("Finding finding-1 is a screening signal. The timeline shows an office.")]})
    observer = NovaVideoObserver(client, "nova")
    result = BedrockCaseAssistant(client, "haiku", observer).answer("What is in the video?", {
        "findings": [FINDING], "video": VIDEO,
        "observations": {"segments": [{"start": 0, "end": 10, "scene": "office"}], "limitations": []},
        "history": [{"role": "assistant", "text": "dropped"}, {"role": "user", "text": "Earlier"}],
    })
    assert result["provider"] == "bedrock"
    assert result["citations"] == [{"finding_id": "finding-1", "start_time": 2.0}]
    request = client.calls[0]
    assert request["modelId"] == "haiku"
    assert [m["role"] for m in request["messages"]] == ["user", "assistant", "user"]
    prompt = request["messages"][-1]["content"][0]["text"]
    assert "office" in prompt and "not findings" in prompt
    assert all("video" not in block for m in request["messages"] for block in m["content"])


def test_answer_model_inspects_a_range_with_the_video_model():
    client = FakeBedrock({
        "haiku": [tool_use("t1", 4, 9, "Is there a cut?"), text("The video model saw a hard cut at about 8s.")],
        "nova": [text("A hard cut occurs at 8.0s.")],
    })
    result = BedrockCaseAssistant(client, "haiku", NovaVideoObserver(client, "nova")).answer(
        "Is there an edit near 8 seconds?", {"findings": [], "video": VIDEO, "observations": None})
    assert result["provider"] == "bedrock"
    assert "hard cut" in result["answer"]
    nova = client.calls[1]
    assert nova["modelId"] == "nova" and "4.0s to 9.0s" in nova["messages"][0]["content"][1]["text"]
    follow_up = client.calls[2]["messages"][-1]["content"][0]["toolResult"]
    assert follow_up["toolUseId"] == "t1" and "not findings" in follow_up["content"][0]["text"]


def test_tool_budget_forces_a_final_answer_without_tools():
    client = FakeBedrock({
        "haiku": [tool_use("t1", 0, 5, "a"), tool_use("t2", 5, 10, "b"), text("I cannot tell from the picture.")],
        "nova": [text("first"), text("second")],
    })
    result = BedrockCaseAssistant(client, "haiku", NovaVideoObserver(client, "nova"), max_tool_calls=2).answer(
        "What happens?", {"findings": [], "video": VIDEO})
    assert result["answer"] == "I cannot tell from the picture."
    final = client.calls[-1]
    assert "toolConfig" not in final
    flattened = json.dumps(final["messages"])
    assert "toolUse" not in flattened and "toolResult" not in flattened and "second" in flattened


def test_audio_only_case_offers_no_tool():
    client = FakeBedrock({"haiku": [text("No automated findings.")]})
    result = BedrockCaseAssistant(client, "haiku", NovaVideoObserver(client, "nova")).answer(
        "Summarize.", {"findings": [], "video": None})
    assert result["provider"] == "bedrock-without-media"
    assert "toolConfig" not in client.calls[0]


def test_unavailable_answer_model_falls_back_to_the_rules_assistant():
    client = FakeBedrock({"haiku": [RuntimeError("AccessDeniedException")]})
    result = BedrockCaseAssistant(client, "haiku").answer("Is this fake?", {"findings": [], "history": []})
    assert result["provider"] == "rules"
    assert "cannot establish" in result["answer"]
    assert "case record only" in result["answer"]
