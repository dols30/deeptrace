"""Leakage-safe synthetic-video benchmark from cached per-video predictions.

Inference is intentionally outside the production API. Populate ``frame_scores``
and (optionally) ``temporal_score`` in the manifest, then run this module. This
keeps expensive predictions reusable and makes validation/test isolation easy
to audit.
"""
from __future__ import annotations

import argparse, csv, json, math, statistics, time
from collections import defaultdict
from pathlib import Path

AGGREGATIONS = ("mean", "median", "max", "p90", "high_score_fraction")


def aggregate(scores: list[float], high_score_threshold: float = 0.5) -> dict[str, float]:
    if not scores or any(not 0 <= value <= 1 for value in scores):
        raise ValueError("frame_scores must be a non-empty list in [0,1]")
    ordered = sorted(scores)
    rank = max(0, math.ceil(0.9 * len(ordered)) - 1)
    return {"mean": statistics.fmean(scores), "median": statistics.median(scores),
        "max": max(scores), "p90": ordered[rank],
        "high_score_fraction": sum(value >= high_score_threshold for value in scores) / len(scores)}


def confusion(labels: list[int], scores: list[float], threshold: float) -> dict[str, int]:
    result = {"tp": 0, "tn": 0, "fp": 0, "fn": 0}
    for label, score in zip(labels, scores):
        result[("t" if (score >= threshold) == bool(label) else "f") + ("p" if score >= threshold else "n")] += 1
    return result


def roc_auc(labels: list[int], scores: list[float]) -> float:
    positives = [s for y, s in zip(labels, scores) if y]
    negatives = [s for y, s in zip(labels, scores) if not y]
    if not positives or not negatives: return float("nan")
    return sum((p > n) + 0.5 * (p == n) for p in positives for n in negatives) / (len(positives) * len(negatives))


def average_precision(labels: list[int], scores: list[float]) -> float:
    positives = sum(labels)
    if not positives: return float("nan")
    ranked = sorted(zip(scores, labels), reverse=True)
    hits = 0
    return sum((hits := hits + label) / rank for rank, (_, label) in enumerate(ranked, 1) if label) / positives


def select_threshold(labels: list[int], scores: list[float], max_fpr: float) -> float:
    """Choose on validation only: highest TPR, then lowest FPR, under the FPR cap."""
    candidates = sorted(set(scores), reverse=True) + [math.nextafter(max(scores), math.inf)]
    feasible = []
    for threshold in candidates:
        c = confusion(labels, scores, threshold); neg, pos = c["tn"] + c["fp"], c["tp"] + c["fn"]
        fpr, tpr = c["fp"] / neg if neg else 0, c["tp"] / pos if pos else 0
        if fpr <= max_fpr: feasible.append((tpr, -fpr, -threshold, threshold))
    if not feasible: raise ValueError("no threshold satisfies requested validation FPR")
    return max(feasible)[-1]


def metrics(labels: list[int], scores: list[float], threshold: float) -> dict[str, float | int | dict]:
    c = confusion(labels, scores, threshold); tp, tn, fp, fn = (c[k] for k in ("tp", "tn", "fp", "fn"))
    safe = lambda n, d: n / d if d else float("nan")
    precision, recall, specificity = safe(tp, tp + fp), safe(tp, tp + fn), safe(tn, tn + fp)
    return {"auroc": roc_auc(labels, scores), "auprc": average_precision(labels, scores),
        "accuracy": safe(tp + tn, tp + tn + fp + fn),
        "balanced_accuracy": (recall + specificity) / 2, "precision": precision, "recall_tpr": recall,
        "specificity": specificity, "fpr": safe(fp, fp + tn), "fnr": safe(fn, fn + tp),
        "f1": safe(2 * precision * recall, precision + recall), "threshold": threshold, "confusion_matrix": c}


def load_manifest(path: Path) -> list[dict]:
    rows = list(csv.DictReader(path.open(newline="")))
    required = {"video_id", "path", "label", "task", "generator", "dataset", "scenario",
        "degradation", "source_id", "split", "frame_scores"}
    if not rows or not required <= set(rows[0]): raise ValueError("manifest is empty or missing required columns")
    groups: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if row["label"] not in {"real", "synthetic"} or row["split"] not in {"validation", "test"}:
            raise ValueError("label must be real/synthetic and split must be validation/test")
        groups[row["source_id"]].add(row["split"])
        row["label_int"] = int(row["label"] == "synthetic")
        row["frame_scores"] = json.loads(row["frame_scores"])
        row["community_forensics"] = aggregate(row["frame_scores"])
        row["temporal_score"] = float(row["temporal_score"]) if row.get("temporal_score") else None
    if any(len(splits) != 1 for splits in groups.values()):
        raise ValueError("split leakage: all variants of a source_id must remain in one split")
    return rows


def run(manifest: Path, output: Path) -> None:
    rows = load_manifest(manifest); output.mkdir(parents=True, exist_ok=True)
    validation = [r for r in rows if r["split"] == "validation"]
    test = [r for r in rows if r["split"] == "test"]
    if not validation or not test: raise ValueError("both validation and test rows are required")
    labels_v = [r["label_int"] for r in validation]
    analysis = []
    for name in AGGREGATIONS:
        scores = [r["community_forensics"][name] for r in validation]
        analysis.append({"aggregation": name, "validation_auroc": roc_auc(labels_v, scores),
            "validation_auprc": average_precision(labels_v, scores)})
    selected = max(analysis, key=lambda item: (item["validation_auroc"], item["validation_auprc"]))["aggregation"]
    thresholds, results = {}, {}
    for model, getter in (("community_forensics", lambda r: r["community_forensics"][selected]),
                          ("temporal_detector", lambda r: r["temporal_score"])):
        usable_v = [r for r in validation if getter(r) is not None]; usable_t = [r for r in test if getter(r) is not None]
        if not usable_v or not usable_t: continue
        lv, sv = [r["label_int"] for r in usable_v], [getter(r) for r in usable_v]
        lt, st = [r["label_int"] for r in usable_t], [getter(r) for r in usable_t]
        thresholds[model] = {"selected_on": "validation", "target_fpr_10": select_threshold(lv, sv, .10),
            "target_fpr_05": select_threshold(lv, sv, .05)}
        results[model] = metrics(lt, st, thresholds[model]["target_fpr_10"])
        results[model]["tpr_at_5pct_fpr_threshold"] = metrics(lt, st, thresholds[model]["target_fpr_05"])["recall_tpr"]
    (output / "metrics.json").write_text(json.dumps(results, indent=2, allow_nan=True))
    (output / "thresholds.json").write_text(json.dumps({"community_aggregation": selected, **thresholds}, indent=2))
    with (output / "aggregation_analysis.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=analysis[0]); writer.writeheader(); writer.writerows(analysis)
    with (output / "predictions.csv").open("w", newline="") as handle:
        fields = ["video_id", "path", "label", "task", "generator", "dataset", "scenario", "degradation", "source_id", "split",
            "community_frame_scores", *AGGREGATIONS, "selected_aggregation", "selected_video_score", "temporal_score"]
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader()
        for row in rows:
            writer.writerow({"video_id": row["video_id"], "path": row["path"], "label": row["label"],
                "task": row["task"], "generator": row["generator"], "dataset": row["dataset"],
                "scenario": row["scenario"], "degradation": row["degradation"],
                "source_id": row["source_id"], "split": row["split"], "community_frame_scores": json.dumps(row["frame_scores"]),
                **row["community_forensics"], "selected_aggregation": selected,
                "selected_video_score": row["community_forensics"][selected], "temporal_score": row["temporal_score"]})
    # Empty, schema-stable research outputs are explicit rather than fabricated.
    for name in ("generator_breakdown.csv", "degradation_breakdown.csv", "scenario_breakdown.csv", "latency.csv", "temporal_sensitivity.csv"):
        (output / name).write_text("condition,model,n,auroc\n")
    (output / "plots").mkdir(exist_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--models", default="community_forensics,temporal_detector")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); run(args.manifest, args.output)


if __name__ == "__main__": main()
