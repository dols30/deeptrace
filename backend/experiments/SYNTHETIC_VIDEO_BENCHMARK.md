# Synthetic-video benchmark

This evaluation module is isolated from `deeptrace.api`; it cannot replace a production detector.

Run from `backend/`:

```bash
python -m experiments.synthetic_video_benchmark \
  --manifest experiments/synthetic_video_manifest.example.csv \
  --models community_forensics,temporal_detector \
  --output results/synthetic_video_benchmark
```

The manifest stores provenance plus cached Community Forensics frame scores and an optional temporal-detector score. All degradation variants reuse the original `video_id`; the loader rejects any `video_id` spanning validation and test. Validation chooses the Community Forensics aggregation and the thresholds targeting FPR ≤10% and ≤5%. Those choices are frozen before test metrics are calculated.

DeMamba is not currently executable in this repository. Its official repository is Apache-2.0 and contains model/training code, but its public README still marks source/dataset release work as incomplete and provides no official pretrained checkpoint. Therefore no DeMamba result has been invented or run. A challenger adapter should be added only after an official, reproducible checkpoint and preprocessing contract are available and reviewed.

The runner emits reusable predictions, aggregation analysis, frozen thresholds, and test metrics. Breakdown/latency/temporal-sensitivity files are created with stable headers and remain empty until those experiments are actually supplied. Production Community Forensics aggregation remains the arithmetic mean regardless of research selection.
