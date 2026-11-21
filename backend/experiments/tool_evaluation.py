"""File-level evaluation of the existing report overview, without score fusion.

This mirrors frontend/lib/report-presentation.ts assessment(); parity cases are
shared with its frontend test. It evaluates reports, never fits a decision rule.
"""
from __future__ import annotations

from collections import Counter
import math

RULE_VERSION = "report_overview_any_detector_v1"


def _score(component):
    value = component.get("raw_score")
    if value is None:
        value = component.get("synthetic_confidence")
    return value if isinstance(value, (int, float)) and math.isfinite(value) else None


def _threshold(component):
    value = component.get("threshold")
    return value if isinstance(value, (int, float)) and math.isfinite(value) else None


def _elevated(anomalies):
    return any(a.get("code", "").startswith("ELEVATED_") for a in anomalies)


def component_flagged(component):
    value, threshold = _score(component), _threshold(component)
    return component.get("status") == "functional" and bool(
        _elevated(component.get("anomalies", []))
        or (value is not None and threshold is not None and value >= threshold)
        or component.get("timestamps_seconds", [])
    )


def assessment(report):
    components = report.get("components", [])
    applicable = [c for c in components if c.get("status") != "not_applicable"]
    missing = sum(c.get("status") != "functional" or _score(c) is None
                  or (not component_flagged(c) and _threshold(c) is None) for c in applicable)
    limited = any(a.get("code") == "LIMITED_FACE_COVERAGE" for a in report.get("anomalies", [])) or any(
        a.get("code") == "LIMITED_FACE_COVERAGE" for c in components for a in c.get("anomalies", []))
    if any(c.get("status") == "stub" for c in components):
        decision, tone = "demo", "neutral"
    elif any(map(component_flagged, components)) or _elevated(report.get("anomalies", [])):
        decision, tone = "flagged", "review"
    elif not applicable or missing or limited:
        decision, tone = "incomplete", "incomplete"
    else:
        decision, tone = "not_flagged", "neutral"
    return {"rule_version": RULE_VERSION, "decision": decision, "tone": tone,
            "missing_checks": missing, "limited_face_coverage": limited,
            "flagging_detectors": [c.get("detector_id") or c.get("model_name") for c in components if component_flagged(c)]}


def metrics(records):
    """Every submitted file counts once; abstentions/errors cannot count correct."""
    if not records or len({r["id"] for r in records}) != len(records):
        raise ValueError("Expected nonempty records with unique file IDs")
    if any(type(r["label"]) is not int or r["label"] not in (0, 1) for r in records):
        raise ValueError("Labels must be integer 0=genuine or 1=manipulated")
    counts = {"tp": 0, "tn": 0, "fp": 0, "fn": 0}
    abstentions = Counter()
    for row in records:
        decision = row["assessment"]["decision"]
        if decision not in ("flagged", "not_flagged", "incomplete", "demo", "error"):
            raise ValueError("Unknown assessment decision")
        if decision in ("incomplete", "demo", "error"):
            abstentions["manipulated" if row["label"] else "genuine"] += 1
            continue
        positive = decision == "flagged"
        counts[("t" if positive == bool(row["label"]) else "f") + ("p" if positive else "n")] += 1
    total = len(records)
    genuine = sum(r["label"] == 0 for r in records)
    manipulated = total - genuine
    decided = sum(counts.values())
    fpr = counts["fp"] / genuine if genuine else None
    decided_genuine = counts["fp"] + counts["tn"]
    decided_fpr = counts["fp"] / decided_genuine if decided_genuine else None
    accuracy = (counts["tp"] + counts["tn"]) / total
    return {"files": total, "genuine": genuine, "manipulated": manipulated,
            "source_groups": len({r["source_group"] for r in records}), "confusion_matrix_decidable": counts,
            "abstentions_or_errors_by_label": dict(abstentions), "decision_coverage": decided / total,
            "accuracy_counting_incomplete_incorrect": accuracy,
            "accuracy_on_decidable": (counts["tp"] + counts["tn"]) / decided if decided else None,
            "false_positive_rate_all_genuine": fpr,
            "false_positive_rate_decidable_genuine": decided_fpr,
            "manipulation_recall_all_manipulated": counts["tp"] / manipulated if manipulated else None,
            "reports_generated": sum(bool(r.get("report_generated")) for r in records),
            "reports_retrieved": sum(bool(r.get("report_retrieved")) for r in records),
            "workspaces_retrieved": sum(bool(r.get("workspace_retrieved")) for r in records),
            "subset_numeric_targets_met": bool(genuine and manipulated and decided == total and accuracy >= .85 and fpr < .10),
            "poc_acceptance_established": False}


def summarize(records):
    return {"rule_version": RULE_VERSION, "overall": metrics(records),
            "by_category": {category: metrics([r for r in records if r["category"] == category])
                            for category in sorted({r["category"] for r in records})},
            "note": "File-level flags, not averaged model percentages or a fused score. Missing decisions count incorrect; flagged partial assessments retain their missing-check count. No agency acceptance is inferred."}


WORKSPACE_RULE_VERSION = 'workspace_officer_any_finding_or_score_v1'


def workspace_assessment_v2(analysis, detector_lookup=None):
    """Coverage-aware workspace rule; v1 remains available to replay archived evidence."""
    result = workspace_assessment(analysis, detector_lookup)
    limited = False
    import re
    for run in analysis.get('model_runs', []):
        if run.get('status') == 'not_applicable':
            continue
        coverage = run.get('coverage') or {}
        limited |= bool(run.get('coverage_limited') or (coverage.get('mode') == 'face_alignment_v1'
                         and coverage['frames_scored'] * 2 < coverage['frames_sampled']))
        for note in run.get('notes', []):
            match = re.match(r'^Scored (\d+) of (\d+) sampled frames', note)
            limited |= note == 'LIMITED_FACE_COVERAGE' or bool(match and int(match[1]) * 2 < int(match[2]))
    result.update(rule_version='workspace_officer_any_finding_or_score_v2', limited_face_coverage=limited)
    if result['decision'] == 'not_flagged' and limited:
        result.update(decision='incomplete', tone='incomplete', title='Screening incomplete')
    return result


def workspace_assessment(analysis, detector_lookup=None):
    """Mirror OfficerSummary for persisted workflow results, including its coverage behavior.

    Deliberately distinct from assessment(): the current workspace does not gate a
    functional, unflagged result on LIMITED_FACE_COVERAGE. Shared fixtures render
    the actual React component to protect this benchmark from silently diverging.
    """
    detector_lookup = detector_lookup or {}
    runs = analysis.get('model_runs', [])
    findings = analysis.get('findings', [])

    def completed(run):
        score = run.get('raw_score')
        return run.get('status') == 'functional' and type(score) in (int, float) and math.isfinite(score)

    def flagged(run):
        matched = any(f.get('model_name') == run.get('model_name') and f.get('modality') == run.get('modality') for f in findings)
        threshold = run.get('threshold')
        return matched or (completed(run) and type(threshold) in (int, float) and run['raw_score'] >= threshold)

    applicable = [r for r in runs if r.get('status') != 'not_applicable']
    missing = sum(not completed(r) for r in applicable)
    demo = analysis.get('development_mock') or any(r.get('development_mock') for r in runs)
    has_flags = bool(findings) or any(flagged(r) for r in runs)
    if demo:
        decision, tone, title = 'demo', 'neutral', 'Demonstration results only'
    elif has_flags:
        decision, tone, title = 'flagged', 'review', 'Signs of possible manipulation flagged'
    elif not applicable or missing:
        decision, tone, title = 'incomplete', 'incomplete', 'Screening incomplete'
    else:
        decision, tone, title = 'not_flagged', 'neutral', 'No signs of manipulation flagged'
    keys = {(r.get('model_name'), r.get('modality')) for r in runs if flagged(r)}
    keys.update((f.get('model_name'), f.get('modality')) for f in findings)
    return {'rule_version': WORKSPACE_RULE_VERSION, 'decision': decision, 'tone': tone, 'title': title,
            'missing_checks': missing, 'flagging_models': sorted({k[0] for k in keys if k[0]}),
            'flagging_detectors': sorted({detector_lookup.get(k) or k[0] for k in keys if k[0]})}
