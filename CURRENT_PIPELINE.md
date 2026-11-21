# DeepTrace current scoring audit

> Dated audit snapshot. The maintained reference is [`docs/MODEL_REGISTRY.md`](docs/MODEL_REGISTRY.md).

This document traces the production code as of 2026-10-03. The active detectors remain DeepfakeBench EfficientNet-B4, Community Forensics ViT-S/16, and AASIST. No experimental model is wired into the API.

## Shared media preparation

`POST /v1/analyze` saves the received bytes, calculates SHA-256, and probes metadata. For video, `deeptrace.media.prepare_video` invokes ffmpeg to write JPEG frames at `1 / DEEPTRACE_FRAME_INTERVAL_SECONDS` (currently one frame per second, capped by `DEEPTRACE_MAX_FRAMES`) and extracts mono 16 kHz WAV audio. The sampled JPEGs are shared inputs, but each visual detector preprocesses them independently.

## Face manipulation — DeepfakeBench EfficientNet-B4

- Task: `face_manipulation` — evidence of manipulation in a detected human face.
- Code: `scripts/inference/efficientnetb4.py`; vendored DeepfakeBench revision `f188b1c105465e2e5377eb536a95022ae0e4522d`.
- Checkpoint: `models/efficientnetb4/effnb4_best.pth`, identified at runtime by SHA-256. The 81-landmark predictor is separately hash-identified.
- Input: dlib frontal-face detection with one upsample; only the largest face in each frame is retained. DeepfakeBench's 81-landmark extraction and similarity warp produce one aligned 256×256 crop. Frames without an alignable face abstain. Multiple faces are **not** aggregated: all but the largest are ignored.
- Pixel transform: BGR→RGB, `[0,255]`→`[0,1]`, then `(x - 0.5) / 0.5`.
- Raw output: two logits ordered `[real, fake]`. Score = `softmax(logits)[1]`; higher means more fake-class evidence. This softmax is not calibrated for DPS media.
- Aggregation: unweighted arithmetic mean of scored aligned-face frame scores. Timestamps preserve original sampled-frame indices. This is current DeepTrace behavior; DeepfakeBench's training/test utilities primarily report per-image predictions and do not establish a DPS video aggregation rule.
- Development decision rule: a frame score ≥0.5 produces an observation. The video score remains the mean. Source: default two-class model decision rule, not a validated DPS threshold.
- Attribution: optional Grad-CAM on `EfficientNetB4.features` for fake logit 1. The returned map is model sensitivity on the aligned crop, not proof of editing.

## AI-generated video — Community Forensics ViT-S/16

- Task: `synthetic_video` — visual evidence consistent with generated imagery in independently sampled frames.
- Code: `scripts/inference/commfor.py`.
- Checkpoint: `models/commfor/frontier.safetensors`; configured revision `16db135220b318d811b207db576d90368980b595`. Config records base model `OwensLab/commfor-model-384` revision `6076002bf0d9dd37537f965ee2f06f826c333b61` and MIT license.
- Input: each whole RGB frame is resized so its short edge is 440 px, center-cropped to 384×384, converted to `[0,1]`, and ImageNet-normalized. It is a `vit_small_patch16_384` image model and does not model frame order or motion.
- Raw output: one logit. The shipped config supplies raw-logit boundary `b=1.359375`. Score = `sigmoid(logit - b)`, so 0.5 corresponds to that release boundary. The config explicitly marks validation invalid; the score is not a calibrated probability and the release boundary is not a DPS threshold.
- Aggregation: unweighted arithmetic mean of sampled-frame scores (`mean_frame_score`). Production behavior is unchanged. The research benchmark additionally records median, maximum, p90, and high-score fraction without promoting them to production.
- Development decision rule: aggregate mean ≥0.5 creates an observation. Frame scores ≥0.5 are retained as review timestamps only when the mean is elevated. This is not DPS-validated.
- Attribution: none is fabricated. The current adapter returns frame scores/logits, not transformer attribution.

## Audio spoof — AASIST

- Task: `audio_spoof` — evidence consistent with spoofed or synthetic speech.
- Code: `scripts/inference/aasist.py`; vendored official AASIST revision `a04c9863f63d44471dde8a6abcb3b082b07cd1d1`.
- Checkpoint: `models/aasist/AASIST.pth`, identified at runtime by SHA-256; architecture comes from the checkpoint variant's official JSON config.
- Input: mono 16 kHz waveform. The official `pad` function produces exactly 64,600 samples (4.0375 s): longer files are truncated and shorter files are repeat-padded.
- Raw output: two logits. In this official configuration class index 0 is spoof and index 1 is bona fide. Score = `softmax(logits)[0]`; higher means more spoof-class evidence. It is an uncalibrated file-level score.
- Aggregation: none across clips; the first 4.0375 s produces one file score.
- Development decision rule: score ≥0.5. This is the default two-class rule, not the ASVspoof EER operating point and not DPS-validated.
- Attribution: optional temporal occlusion and secondary experimental relevance data. These explain sensitivity of the analyzed input only.

## API, storage, report, and UI semantics

The API returns three independent `ComponentResult` objects. New semantic fields include detector ID/name, task, raw/display score, nullable calibrated probability, threshold provenance/validation, aggregation method, sample count, and sample scores. `synthetic_confidence` remains as a deprecated compatibility alias for old stored reports.

`overall_synthetic_confidence` also remains readable for schema/storage compatibility but new reports set it to `null`. No arithmetic average or weighted fusion is calculated. Reports contain an evidence summary and deterministic prose instead. The UI and PDF label values **Model score**, show separate face, generated-video, and audio cards, and show separate visual timelines. All current thresholds are labeled “development/default model decision rule” and “Threshold not yet DPS-validated.”

Database model runs store raw score separately from nullable calibrated probability. Existing workflow tables retain their legacy numeric threshold column; the API metadata is authoritative about whether that threshold is validated.

## Current threshold audit

| Detector | Displayed value | Current rule | Source | DPS validated? | Calibrated? |
|---|---|---:|---|---|---|
| EfficientNet-B4 | Mean aligned-face frame softmax(fake) | 0.5 per-frame observation | default model decision rule | No | No |
| Community Forensics | Mean of `sigmoid(logit - 1.359375)` frame scores | 0.5 aggregate observation | release raw-logit boundary mapped to 0.5; config validation flag is false | No | No |
| AASIST | `softmax(logits)[spoof=0]` on first 64,600 samples | 0.5 | default model decision rule | No | No |

DeepTrace outputs are AI-assisted indicators intended to support investigator review. A flagged result does not establish that media is manipulated, and a non-flagged result does not establish authenticity.
