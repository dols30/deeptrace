"""Case assistant. Answers only from the supplied analysis context."""

from typing import Protocol

REFUSAL = (
    "DeepTrace cannot establish that this media is authentic or manipulated. "
    "Model outputs are advisory screening signals and require human interpretation."
)


class CaseAssistant(Protocol):
    def answer(self, question: str, context: dict) -> dict: ...


class RulesCaseAssistant:
    """Deterministic assistant. An LLM provider can replace this class."""

    def answer(self, question: str, context: dict) -> dict:
        text = question.strip().lower()
        findings = context.get("findings") or []
        if _asks_for_proof(text):
            return _reply(REFUSAL, [])
        if "aasist" in text or "occlusion" in text or "segment" in text or "timeline" in text:
            return _reply(_audio_segments(findings), [item for item in findings if item.get("windows")])
        if "attribution" in text:
            return _reply(
                "An attribution visualization shows parts of the model input that influenced the prediction. "
                "It does not prove manipulation occurred in that region.",
                [item["id"] for item in findings if item.get("attribution_method")],
            )
        if "disagree" in text:
            selected = [item for item in findings if item.get("human_disposition") == "disagree"]
            return _reply(_list_findings("Findings you marked Disagree", selected, "No reviewed finding is marked Disagree."), selected)
        if "expert" in text:
            selected = [item for item in findings if item.get("human_disposition") == "needs_expert_review"]
            return _reply(_list_findings("Findings marked Needs Expert Review", selected, "No finding is marked Needs Expert Review."), selected)
        if "highest" in text and "video" in text:
            selected = sorted((item for item in findings if item["modality"] == "video"), key=lambda item: item["raw_score"], reverse=True)[:3]
            return _reply(_list_findings("Highest scoring video findings", selected, "No video finding exceeded the decision threshold."), selected)
        if "draft" in text or "summary" in text and "review" in text:
            reviewed = [item for item in findings if item.get("human_disposition")]
            return _reply(_draft(reviewed), reviewed or findings)
        if "portion" in text or "which" in text and "review" in text:
            return _reply(_list_findings("Portions to review", findings, "No automated finding exceeded the decision threshold."), findings)
        if "summar" in text or "finding" in text:
            return _reply(_list_findings("Automated findings in this analysis", findings, "This analysis has no automated findings above the decision threshold."), findings)
        return _reply(
            "I can only answer from this analysis. Ask about the findings, dispositions, AASIST, or an attribution view.",
            [],
        )


def _asks_for_proof(text: str) -> bool:
    markers = ("confirm", "prove", "is it fake", "is this fake", "deepfake confirmed", "authentic")
    return any(marker in text for marker in markers)


def _audio_segments(findings: list[dict]) -> str:
    explained = [item for item in findings if item.get("windows")]
    if not explained:
        scores = [
            f"Finding {item['id']} file screening score {item['raw_score']:.2f}."
            for item in findings if item.get("modality") == "audio"
        ]
        prefix = (" ".join(scores) + " ") if scores else ""
        return (
            prefix + "Temporal occlusion was not produced for this analysis. "
            "The file-level screening score stands without a timeline. " + REFUSAL
        )
    lines = [
        "Temporal occlusion is the stored audio explanation. "
        "A score_delta is the change in the spoof screening score when that span was masked. "
        "It is not evidence that the span was synthesized."
    ]
    for item in explained:
        windows = item["windows"]
        top = max(windows, key=lambda window: window.get("score_delta") or 0)
        fill = top.get("fill") or "the stored fill"
        lines.append(
            f"Finding {item['id']}: masking {top['start']:.3f}s–{top['end']:.3f}s "
            f"with {fill} changed the model screening score by {top['score_delta']:.3f}."
        )
        if item.get("fill_rankings_agree") is False:
            lines.append("The other stored fills do not rank the windows the same way. That disagreement is kept.")
    lines.append(REFUSAL)
    return " ".join(lines)


def _list_findings(title: str, findings: list[dict], empty: str) -> str:
    if not findings:
        return empty + " " + REFUSAL
    lines = [title + ". These are model findings, not investigator conclusions."]
    for item in findings:
        end = item.get("end_time")
        span = f"{item['start_time']:.1f}s" if end is None else f"{item['start_time']:.1f}s–{end:.1f}s"
        disposition = item.get("human_disposition") or "not reviewed"
        lines.append(
            f"Finding {item['id']} ({item['modality']}, {span}): possible manipulation signal, "
            f"model score {item['raw_score']:.2f}, investigator disposition {disposition}."
        )
    lines.append(REFUSAL)
    return " ".join(lines)


def _draft(reviewed: list[dict]) -> str:
    if not reviewed:
        return "A screening summary should use findings you have reviewed. None have a disposition yet. " + REFUSAL
    return _list_findings("Draft screening summary from reviewed findings", reviewed, "")


def _reply(answer: str, findings: list[dict] | list[str]) -> dict:
    citations = []
    for item in findings:
        if isinstance(item, str):
            citations.append({"finding_id": item})
        else:
            citations.append({"finding_id": item["id"], "start_time": item["start_time"]})
    return {"answer": answer, "citations": citations, "advisory_only": True, "provider": "rules"}


class LLMCaseAssistant:
    """Replace the generate method with a provider call. The prompt boundary stays here."""

    def __init__(self, fallback: CaseAssistant | None = None):
        self.fallback = fallback or RulesCaseAssistant()

    def answer(self, question: str, context: dict) -> dict:
        return self.fallback.answer(question, context)
