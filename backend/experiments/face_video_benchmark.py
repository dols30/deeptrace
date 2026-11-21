"""Evaluate cached EfficientNet-B4 and FakeSTormer predictions on identical videos."""
from __future__ import annotations

import argparse, csv, json
from pathlib import Path

from experiments.synthetic_video_benchmark import metrics, select_threshold


def load_manifest(path: Path) -> list[dict]:
    rows = list(csv.DictReader(path.open(newline="")))
    required = {"video_id", "path", "label", "task", "generator", "dataset", "scenario",
        "degradation", "source_id", "split", "efficientnet_score", "fakestormer_score"}
    if not rows or not required <= set(rows[0]): raise ValueError("manifest is empty or missing required columns")
    sources: dict[str, set[str]] = {}
    for row in rows:
        if row["task"] != "face_manipulation": raise ValueError("face benchmark requires task=face_manipulation")
        if row["label"] not in {"real", "manipulated"}: raise ValueError("label must be real/manipulated")
        if row["split"] not in {"validation", "test"}: raise ValueError("split must be validation/test")
        sources.setdefault(row["source_id"], set()).add(row["split"])
        row["label_int"] = int(row["label"] == "manipulated")
        for name in ("efficientnet_score", "fakestormer_score"):
            row[name] = float(row[name]) if row[name] else None
    if any(len(splits) != 1 for splits in sources.values()):
        raise ValueError("split leakage: all variants of a source_id must remain in one split")
    return rows


def run(manifest: Path, output: Path) -> None:
    rows = load_manifest(manifest); output.mkdir(parents=True, exist_ok=True)
    validation, test = ([r for r in rows if r["split"] == split] for split in ("validation", "test"))
    if not validation or not test: raise ValueError("both validation and test rows are required")
    thresholds, report = {}, {}
    for detector in ("efficientnet_score", "fakestormer_score"):
        val = [r for r in validation if r[detector] is not None]; held = [r for r in test if r[detector] is not None]
        if not val or not held: continue
        labels_v, scores_v = [r["label_int"] for r in val], [r[detector] for r in val]
        labels_t, scores_t = [r["label_int"] for r in held], [r[detector] for r in held]
        t10, t05 = select_threshold(labels_v, scores_v, .10), select_threshold(labels_v, scores_v, .05)
        thresholds[detector] = {"selected_on": "validation", "target_fpr_10": t10, "target_fpr_05": t05}
        report[detector] = metrics(labels_t, scores_t, t10)
        report[detector]["tpr_at_5pct_fpr_threshold"] = metrics(labels_t, scores_t, t05)["recall_tpr"]
    (output / "metrics.json").write_text(json.dumps(report, indent=2, allow_nan=True))
    (output / "thresholds.json").write_text(json.dumps(thresholds, indent=2))
    (output / "dataset_summary.json").write_text(json.dumps({"rows": len(rows),
        "validation": len(validation), "test": len(test),
        "datasets": sorted(set(r["dataset"] for r in rows))}, indent=2))
    with (output / "predictions.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys())); writer.writeheader(); writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); run(args.manifest, args.output)


if __name__ == "__main__": main()
