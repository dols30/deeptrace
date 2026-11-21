# Model scoring semantics

No score below is a calibrated probability of manipulation. Production UI terminology is **Model Score**.

| Detector | Raw output and orientation | Model-score transform | Video/file aggregation | Decision rule | Calibration |
|---|---|---|---|---|---|
| DeepfakeBench EfficientNet-B4 | Two logits `[real, fake]`; larger fake logit favors manipulation | `softmax(logits)[1]` | Largest dlib-aligned face only per sampled frame; unweighted mean across scored frames | Development rule 0.5; any frame at/above it is surfaced | None |
| FakeSTormer (experimental) | Official base model returns classification, heatmap, and four temporal-location logits; single-video code labels from the last temporal output | `sigmoid(temp_loc)[-1]` | One four-frame temporal clip in the official base c23 configuration | Official config contains 0.5; not DPS-validated | None established |
| Community Forensics ViT-S/16 | One raw synthetic-image logit; larger favors AI-generated | `sigmoid(logit - 1.359375)` using the release boundary | Production: unweighted mean over sampled independent frames | Score 0.5 corresponds to the release logit boundary; config says validation is false; not DPS-validated | Config contains a bias transform, but no valid DPS calibration |
| DeMamba (experimental) | **BLOCKED:** official public release has no reproducible pretrained checkpoint/single-video scoring contract | Not asserted | Not asserted | None | None |
| AASIST | Two logits ordered `[spoof, bona_fide]`; larger class-0 logit favors spoof | `softmax(logits)[0]` | One output from the first 64,600 mono 16 kHz samples (4.0375 s); short audio is repeat-padded | Development two-class rule 0.5; not the published EER operating point and not DPS-validated | None |

## Preprocessing details

### EfficientNet-B4

dlib proposes frontal faces and the largest face is retained. DeepfakeBench predicts 81 landmarks and performs its similarity alignment to 256×256. RGB pixels are scaled to `[0,1]` and normalized with mean/std 0.5. Frames without an alignable face abstain. The current production aggregation is unchanged.

### FakeSTormer

The audited official revision is `c5b5f75100b878212a192c00013275f275f86182`. Its c23 base configuration is a TimeViT with divided space-time attention, 224×224 inputs, patch size 16, 12 layers, 12 heads, and four frames. Official preprocessing uniformly samples faces for evaluation, detects with RetinaFace, retains the largest detection, pads its bounding box by 25%, resizes to 256×256, removes a 15-pixel border in single-video inference, resizes to 224×224, scales to `[0,1]`, and applies ImageNet mean/std. The experimental bridge preserves that path and refuses CPU-only execution.

The official single-video script uses the temporal-location branch rather than the classification branch for its displayed label/score. The adapter records the complete temporal output and uses the last sigmoid value exactly as that script does. This choice must be validated on the intended benchmark before operational interpretation.

### Community Forensics

Each full frame is resized to a 440-pixel short edge, center-cropped to 384×384, and ImageNet-normalized. The model does not receive adjacent frames jointly. The experimental benchmark records mean, median, max, p90, and high-score fraction, selects only on validation, and never changes production aggregation automatically.

### DeMamba

The official repository and paper describe a spatiotemporal Detail Mamba module and GenVideo experiments. Because an official compatible pretrained checkpoint and complete inference contract are unavailable, DeepTrace does not assert frame count, resolution, normalization, positive-class index, or score transform. The adapter returns `blocked` rather than guessing.

### AASIST

Audio is decoded/resampled to mono 16 kHz. The official `pad` routine truncates or repeat-pads to 64,600 samples. Only the first 4.0375 seconds can affect a long-file score.

## Thresholds and status

Raw output, model score, calibrated probability, threshold, and status are separate fields. `calibrated_probability` remains `null` unless a versioned calibration is fitted and evaluated. GREEN/YELLOW/RED statuses are emitted only when review/flag thresholds are explicitly marked validated; otherwise the status is `threshold_not_validated`.
