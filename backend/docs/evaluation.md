# Robustness and domain-shift plan

Question: how do pretrained detector accuracy, AUROC, and false-positive rate change under public/synthetic proxy shifts resembling body-camera, surveillance, interview, radio, and voice-memo conditions?

Evaluate against the current defaults (**DeepfakeBench EfficientNet-B4**, **AASIST/AASIST-L**) and optional alternatives (**Effort**, **Nes2Net**). See [models.md](models.md) for runner setup.

1. Freeze model Git SHAs, checkpoint hashes, thresholds, sampling, and clean held-out splits.
2. Report accuracy, FPR, TPR, AUROC, confusion counts, sample counts, and group-bootstrap confidence intervals.
3. Apply one controlled transformation at a time; keep every transformed derivative in the same split as its source.
4. Compare paired score/metric changes to clean originals and manually categorize errors on a consented/public subset.

| Modality | Shift | Levels |
|---|---|---|
| Video | H.264 | CRF 18, 28, 38 |
| Video | Resolution | 1080p, 720p, 480p, 240p |
| Video | Surveillance proxy | low light/FPS, fixed camera, overlay |
| Video | Bodycam proxy | motion blur, shake, distortion, occlusion |
| Audio | Noise | SNR 20, 10, 0 dB |
| Audio | Radio proxy | ~300–3400 Hz band limit, codec/channel noise |
| Audio | Voice-memo proxy | AAC/Opus transcode and reverberation |

Record exact transforms and provenance in a machine-readable manifest. These are proxy shifts, not authentic operational distributions. Key risks are identity leakage, correlated frames inflating sample size, incorrect score direction, and thresholds tuned on test data.

Seven-week gates (see [roadmap.md](roadmap.md)): reproduce checkpoints by week 2; integrated report by week 3; freeze clean evaluation in week 4; run shifts/error analysis in weeks 5–6; complete reproducibility run and presentation in week 7.

Use `python scripts/benchmark.py scores.csv` for score-level metrics (`id,label,score`, with `1=fake/spoof`). Report at the independent video/utterance level, not per correlated frame.
