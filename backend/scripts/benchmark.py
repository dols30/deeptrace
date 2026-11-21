#!/usr/bin/env python3
import argparse
import csv
import json
from pathlib import Path


def calculate(rows, threshold=0.5):
    labels, scores = [int(r["label"]) for r in rows], [float(r["score"]) for r in rows]
    predicted = [int(score >= threshold) for score in scores]
    tp = sum(a == b == 1 for a, b in zip(labels, predicted)); tn = sum(a == b == 0 for a, b in zip(labels, predicted))
    fp = sum(a == 0 and b == 1 for a, b in zip(labels, predicted)); fn = sum(a == 1 and b == 0 for a, b in zip(labels, predicted))
    pairs = [(p, n) for p, label in zip(scores, labels) if label for n, other in zip(scores, labels) if not other]
    return {"n": len(rows), "threshold": threshold, "accuracy": (tp + tn) / len(rows),
        "false_positive_rate": fp / (fp + tn) if fp + tn else None,
        "true_positive_rate": tp / (tp + fn) if tp + fn else None,
        "auroc": sum((p > n) + .5 * (p == n) for p, n in pairs) / len(pairs) if pairs else None,
        "confusion_matrix": {"tp": tp, "tn": tn, "fp": fp, "fn": fn}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Metrics for CSV columns id,label,score; 1=fake/spoof")
    parser.add_argument("csv_file", type=Path); parser.add_argument("--threshold", type=float, default=.5)
    args = parser.parse_args()
    with args.csv_file.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows or not {"label", "score"}.issubset(rows[0]):
        raise SystemExit("CSV needs at least one row and label,score columns")
    print(json.dumps(calculate(rows, args.threshold), indent=2))
