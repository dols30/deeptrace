# Model registry

Every model DeepTrace can run, what its score means, and where that meaning is created. Setup/environment instructions are in [`backend/docs/models.md`](../backend/docs/models.md); experimental detector setup is in [`experimental_models.md`](experimental_models.md). A dated scoring audit with the same conclusions is in [`CURRENT_PIPELINE.md`](../CURRENT_PIPELINE.md).

## Tasks are not interchangeable

| `task` | Question | Production detector | What it cannot see |
| --- | --- | --- | --- |
| `face_manipulation` | Was a real person's face swapped/reenacted/edited? | DeepfakeBench EfficientNet-B4 | Background, body, text, fully generated scenes, frames with no alignable face |
| `synthetic_video` | Do sampled frames look like fully AI-generated imagery? | Community Forensics ViT-S/16 | Motion/temporal artifacts, frame edges outside the 384 px center crop |
| `audio_spoof` | Is the speech spoofed/synthetic? | AASIST | Anything after the first 4.0375 s of audio |

A quiet score on one task says nothing about the others. Do not merge, average, or max these scores. (`CombinedVideoAnalyzer`, which took the max of face and whole-frame scores, still exists in `analyzers/video.py` but is **not used** by the API.)

## Score vocabulary

- **Model score** (`raw_score` = `display_score` = deprecated `synthetic_confidence`): a softmax or shifted-sigmoid output in [0, 1], oriented 0 = real/bona fide, 1 = fake/spoof. **Uncalibrated. Not a probability.**
- **Calibrated probability** (`calibrated_probability`): always `null` today. Calibration utilities exist (`ml/evaluation.py`: temperature scaling, Platt, ECE, Brier) but no fitted calibration is wired in.
- **Threshold**: portable default `0.5`, `threshold_source="default_model_decision_rule"`. The explicit EfficientNet PoC rule below uses `0.9967585206031799`. All retain `threshold_validated=False`; none is a DPS-validated operating point.
- **operational_status**: `threshold_not_validated` for all detectors; green/yellow/red statuses are computed only when validated review/flag thresholds exist (`schemas.operational_status`), which never happens today.

## Where the score is computed

```text
runner script (scripts/inference/*.py)         → per-sample or file score ("fake_probability" in JSON; a model score, not a probability)
analyzer (deeptrace/analyzers/*.py)             → validates [0,1]; aggregates frames by unweighted mean; recorded per-detector observation rule
ml/detectors.py::detection_from_component       → EfficientNet findings use the component threshold; other workflow findings retain DEEPTRACE_DECISION_THRESHOLD (default 0.5)
reporting.py::build_report                      → no fusion; descriptive component observations only (legacy MODEL_DISAGREEMENT retained on old reports)
```

The JSON key `fake_probability` in the runner contract is historical; the adapters store it as `raw_score` and label it uncalibrated.

---

## Production detectors

### DeepfakeBench EfficientNet-B4 — face manipulation

| Field | Value |
| --- | --- |
| `detector_id` / `task` | `deepfakebench_efficientnet_b4` / `face_manipulation` |
| Selected by | `DEEPTRACE_VIDEO_MODEL=efficientnetb4` (default) + `DEEPTRACE_EFFICIENTNET_COMMAND` |
| Runner / adapter | `backend/scripts/inference/efficientnetb4.py` / `EfficientNetVideoAnalyzer` |
| Upstream code | `SCLBD/DeepfakeBench` @ `f188b1c105465e2e5377eb536a95022ae0e4522d` (cloned to `vendor/` by `scripts/download_models.sh`) |
| Checkpoint | `models/efficientnetb4/effnb4_best.pth` — DeepfakeBench release `v1.0.1`, SHA-256 `74cbd82d…beaf0f` (pinned in `scripts/download_public_assets.sh`). Landmarks: `shape_predictor_81_face_landmarks.dat` (release `v1.0.0`) |
| Training data | FaceForensics++ per upstream DeepfakeBench (runner docstring "strict FF++ weights"). Exact split/compression: **not verified in this repo** |
| License | DeepfakeBench CC BY-NC 4.0 (per `backend/docs/models.md`) |
| Input | Sampled JPEG frames (`frame_%06d.jpg`) |
| Preprocessing | Upstream `preprocessing/preprocess.py::extract_aligned_face_dlib`: dlib frontal detector (1 upsample) → **largest face only** → five keypoints from the 81-point predictor → similarity warp (scale 1.3) to 256×256 → dlib must re-detect a face on the crop, otherwise the frame is dropped. Then BGR→RGB → `/255` → `(x − 0.5) / 0.5`. Frames without an alignable face are skipped (abstain) |
| Output | Two logits `[real, fake]` |
| Score | `softmax(logits)[1]` per aligned face |
| Aggregation | Unweighted mean over scored frames (`aggregation_method="mean_aligned_face_frame_score"`) |
| Observations | `ELEVATED_FRAME_SCORE` if any frame reaches the recorded threshold (portable default 0.5; opt-in PoC rule below); `LIMITED_FACE_COVERAGE` if < 50% of sampled frames were scored |
| Attribution | With `--explain`: Grad-CAM on `EfficientNetB4.features` for logit 1, plus alignment matrix and crop JPEG (`scripts/inference/gradcam.py`, `face_geometry.py`). Model sensitivity, not a manipulation map |
| Loading | `torch.load(weights_only=True)`, `strict=True`, `module.`/`backbone.` prefixes stripped. Missing keys → error |
| Device | `--device cpu` in all shipped commands (`cuda` accepted) |
| Fallback | None. No faces → `status="unavailable"`; runner failure → `status="error"` |
| Limitations | Single largest face; frame-independent (no temporal modeling); uncalibrated on DPS media |

#### Development-selected face PoC rule — November 11, 2026

`DEEPTRACE_EFFICIENTNET_DECISION_RULE=ffpp_c23_kaggle_v1` selects **any aligned frame >= 0.9967585206031799**. Its source is `ffpp_c23_kaggle_v1_development_only_any_frame`; rules are versioned in `deeptrace/ml/decision_rules.py`. This setting changes frame classes, timestamps, elevated observations and new workflow findings consistently. The displayed component score remains the within-detector mean, not the maximum used by the any-frame decision. This opt-in mean is retained at full precision to avoid rounding a below-threshold value above the decision boundary; portable default mean rounding remains unchanged. The API's ordinary default stays `default_0_5`. The explicit `scripts/run_local_poc.py` launcher opts into the PoC rule unless an environment override is supplied. No audio or generated-image threshold is changed.

The rule was selected from 80 development videos (40 genuine/40 manipulated) under a 5% development FPR cap, before the 80-video test. On that test, the default rule gave TP40/TN14/FP26/FN0 (67.5% accuracy, 65% FPR). The frozen PoC rule gave TP36/TN39/FP1/FN4 (**93.75% accuracy, 2.5% FPR, 90% recall**). Four manipulation methods had 10 videos each; source pairs are correlated. Source: Kaggle `abbasaliyev/ffpp-core-c23-videos` v2, fixed c23 selection. User archive SHA256 `a6bf5331369793b36b9e96c0c723ec51b4b7b130719918cd3e061e474a9c810a`; manifest SHA256 `23d95aa0db5a461dfef31289baeb60a23b40f1d875bb84fa4b549e010a0bd24e`. Reproduction/evidence are local ignored `artifacts/poc-kaggle-workspace/verified-face-2026-11-11/` and `verify_face_archive.py`. These measured subset results do not establish operational acceptance or generalization; the released checkpoint's training split remains unknown. No weight training or score calibration occurred. Do not retune on the revealed test.

The opt-in rule requires the recorded EfficientNet source/checkpoint and 81-point landmark identifiers, otherwise the adapter fails closed. Settings require the benchmark's 1-second interval and 120-frame cap. Existing preprocessing, largest-face alignment and score orientation are unchanged. `threshold_validated=False`, calibrated probability remains null, and operational status remains `threshold_not_validated`. New records store their threshold/source; historical reports and findings are not rewritten.

### Community Forensics ViT-S/16 — fully AI-generated imagery

| Field | Value |
| --- | --- |
| `detector_id` / `task` | `community_forensics` / `synthetic_video` |
| Selected by | Always constructed; runs when `DEEPTRACE_SCENE_COMMAND` is set |
| Runner / adapter | `backend/scripts/inference/commfor.py` / `SceneVideoAnalyzer` |
| Checkpoint | `models/commfor/frontier.safetensors` + `config.json`, reported revision `16db135220b318d811b207db576d90368980b595` (`Thermostatic/community-forensics-frontier-detector-2026-08`, fine-tune of `OwensLab/commfor-model-384`, MIT per config). **TODO: no script in the repo downloads this checkpoint**; provenance relies on the local `.sha256`/`.revision` files |
| Training data | Runner docstring: fine-tuned "on recent generators with JPEG/WebP laundering augmentation". Specific datasets: **unknown** |
| Input | Same sampled JPEG frames as the face model |
| Preprocessing | RGB → bilinear resize short edge to 440 → center crop 384×384 → `/255` → ImageNet mean/std |
| Output | One raw logit (`vit_small_patch16_384`, `num_classes=1`) |
| Score | `sigmoid(logit − b)`, `b = raw_logit_boundary` from `config.json` (local file: `1.359375`). 0.5 ≡ release decision boundary. `--config` or `--boundary` is required; no boundary is assumed |
| Aggregation | Unweighted mean of frame scores (`mean_frame_score`) |
| Observations | `ELEVATED_GENERATED_SCENE_SCORE` only when the **mean** ≥ 0.5; frame timestamps are kept only then |
| Not used from config | The local `config.json` also contains `calibration` (bias, intercept ≈ −0.74), `target_probability_threshold: 0.65`, and `validation_valid: false`. The runner ignores calibration and the 0.65 target; do not apply them without validation |
| Attribution | None |
| Loading | safetensors, `vit.` prefix stripped, `strict=True` |
| Device | `cpu` in shipped commands (`cuda`, `mps` accepted) |
| Fallback | None; unset command → `unavailable` |
| Limitations | Still-image model; ignores temporal/codec artifacts; crop discards frame edges |

### AASIST — spoofed / synthetic speech

| Field | Value |
| --- | --- |
| `detector_id` / `task` | `aasist` / `audio_spoof` |
| Selected by | `DEEPTRACE_AUDIO_MODEL=aasist` (default) or `aasist-l` + `DEEPTRACE_AASIST_COMMAND` (`--variant` must match) |
| Runner / adapter | `backend/scripts/inference/aasist.py` / `AASISTAudioAnalyzer` |
| Upstream code | `clovaai/aasist` @ `a04c9863f63d44471dde8a6abcb3b082b07cd1d1`; architecture from `config/AASIST.conf` (or `AASIST-L.conf`) |
| Checkpoint | `models/aasist/AASIST.pth` — Hugging Face mirror `SpeechAntiSpoofingBenchmarks/AASIST` @ `16774d45…`, SHA-256 `51d2d9cf…a1c0`. `backend/experiments/README.md` notes it should be compared with the official upstream checkpoint |
| Training data | ASVspoof 2019 LA (upstream config `track: LA`; [`model-inference-audit.md`](model-inference-audit.md)) |
| Input | Audio file, or the mono 16 kHz WAV extracted from video |
| Preprocessing | `librosa.load(sr=16000, mono=True)` (ffmpeg fallback) → upstream `pad(x, 64600)`: truncate to the **first 64,600 samples (4.0375 s)**, repeat-pad shorter audio |
| Output | Two logits; class 0 = spoof, 1 = bona fide |
| Score | `softmax(logits)[0]` (file-level) |
| Aggregation | None (`file_level_model_output`); one sample spanning the file |
| Observations | `ELEVATED_SPOOF_SCORE` if score ≥ 0.5 |
| Attribution | With `--explain`: 500 ms temporal occlusion (displayed fill `local_mean`, zeros/noise stored), integrated gradients (secondary), graph attention (`scripts/inference/audio_explain.py`) |
| Loading | `weights_only=True`, `strict=True` |
| Device | `cpu` in shipped commands |
| Fallback | None |
| Limitations | Ignores audio after 4.0375 s; 0.5 is not the ASVspoof EER operating point |

---

## Alternative detectors (selectable, not default)

Neither has checkpoints in `models/` in the inspected checkout and neither is in the Docker image.

| | Effort + CLIP-L/14 | Nes2Net-X (speech) |
| --- | --- | --- |
| Task | `face_manipulation` | `audio_spoof` |
| Select | `DEEPTRACE_VIDEO_MODEL=effort`, `DEEPTRACE_EFFORT_COMMAND` | `DEEPTRACE_AUDIO_MODEL=nes2net`, `DEEPTRACE_NES2NET_COMMAND` |
| Runner | `scripts/inference/effort.py` | `scripts/inference/nes2net.py` |
| Upstream | `YZY-stack/Effort-AIGI-Detection` @ `96f5dea2…` | `Liu-Tianchi/Nes2Net_ASVspoof_ITW` @ `c9fe1177…` |
| Checkpoint | FF++ CLIP-L/14 + Effort; local CLIP ViT-L/14 dir; 81-pt landmarks | ASVspoof 19/21 wav2vec2 Nes2Net-X + `xlsr2_300m.pt` |
| Preprocessing | Largest face, upstream dlib alignment at 224 px, upstream `preprocess_face` | librosa 16 kHz mono; `4s` mode tiles/truncates to 64,000 samples, or `full` |
| Score | Upstream `prob` = `softmax(pred)[:, 1]` | `softmax(logits)[0]` (spoof = 0) |
| Adapter quirks | Uses base `VideoCommandAnalyzer` defaults: `detector_id="face_detector"` | `detector_id="audio_spoof_detector"` |

## Experimental detectors (not reachable from the API)

Code in `backend/deeptrace/experimental/` and `backend/experiments/`; result type `ExperimentalDetectorResult`. See [`experimental_models.md`](experimental_models.md) and [`model_scoring.md`](model_scoring.md).

- **FakeSTormer** (`face_manipulation`): official four-frame TimeViT, score = last `sigmoid(temp_loc)` output as the official single-video script does. Requires CUDA environment. SnT academic license.
- **DeMamba** (`synthetic_video`): **BLOCKED** — no reproducible official checkpoint/inference contract. Adapter returns `status="blocked"`.

## Non-detector models

- **Case assistant** (`ml/assistant.py`, `ml/gemini_assistant.py`): default `RulesCaseAssistant` (deterministic, answers from stored findings). Optional Gemini (`DEEPTRACE_GEMINI_MODEL`, default `gemini-2.5-flash`) receives the recording when ≤ 80 MB; falls back to rules on error. It does not produce detection scores.

## Rules for changing models

For contributions, new detectors are opt-in, preserve the runner JSON contract and `ComponentResult` semantics, record checkpoint provenance (URL, revision, SHA-256, license, training data), benchmark at the independent video/utterance level, and never become the default implicitly.


## Extended PoC inference and descriptive methods (October 22, 2026)

The production selectors/checkpoints remain unchanged. `scripts/run_local_poc.py` is an explicit local opt-in profile.

### Full-recording AASIST policy

`DEEPTRACE_AASIST_WINDOW_MODE=full` invokes the same checkpoint on consecutive non-overlapping 64,600-sample windows, with a final repeat-padded short window. Reported intervals exclude padding. Score orientation is unchanged (class 0 spoof softmax). `mean_nonoverlapping_window_score_v1` is the unweighted within-detector window mean; any window >=0.5 produces a review observation/timestamp. No cross-detector fusion or fitted calibration is introduced. Attribution, when requested, covers the first input window only and is not copied to later-window findings. Workflow preprocessing version receives `-full-window-v1`. The default remains `first`.

This changes the analyzed duration and file-level aggregation when opted in. It needs evaluation before any operational promotion. It is not a fitted improvement in accuracy or FPR. Upstream preprocessing reference: https://github.com/clovaai/aasist/blob/main/data_utils.py .

### Supplementary measurements

`review_signals.py` runs in the separate model environment and emits `ReviewCheck` records, not `ComponentResult` scores. It requires no new classifier checkpoint. Its landmark path uses the existing pinned dlib predictor (hash included in the result). Default coverage is the first 30 seconds, bounded at 120 via the CLI; availability and measured coverage are reported per method. Video measurements use original decoded pixels rather than the JPEGs prepared for the image classifiers.

| Method | Actual computation | Unsupported inference |
| --- | --- | --- |
| Generated-image frequency review | Hann-windowed spatial FFT high-frequency energy on native decoded frames, about one sample per second | GAN architecture/artifact identification or localization |
| Eye/blink review | Six-point eye aspect ratio on a largest-face track up to 30 fps; candidate closures below 70% of its median, reset across tracking loss | Unnatural-blinking verdict, identity verification or validated blink count |
| Facial movement | Nose-centered/inter-eye-normalized landmark displacement; discontinuous tracks excluded | Micro-expression classification or proof of biological inconsistency |
| Compression review | 8-pixel boundary/interior luma contrast on native decoded frames | Original codec history, double-compression identification, tamper localization |
| Mel analysis | 64-band power spectrogram, FFT512 / hop160 at16kHz, mean band energies | A trained mel classifier |
| Spectral/vocoder review | Per-second spectral flatness and centroid | Specific vocoder identification or synthetic-speech probability |
| Noise review | Within-block bottom20% RMS frame candidates, 1s blocks, >=20 candidates/block; >=12dB change intervals | Isolated background-noise segmentation or manipulation determination |

All rules are exploratory and `validated=false`. Occlusion, pose, camera/codec processing, rescaling, recording gain and speech/music are confounds. No finding from these measurements is automatically promoted into a synthetic-media decision. Model decisions remain independent.

Method references: [eye aspect ratio paper](https://vision.fe.uni-lj.si/cvww2016/proceedings/papers/05.pdf), [librosa feature implementation](https://librosa.org/doc/0.10.2/feature.html). These references support the measurements, not a claim of deepfake detection performance.

JPEG preparation now explicitly requests full-range yuvj420p for compatibility with the local FFmpeg encoder. Clips shorter than the sampling interval receive a single initial frame when the fps filter otherwise yields none. This preparation change is covered by real-format tests and must be held fixed in future evaluation.

### Optional trained artifact paths

These paths are enabled by the explicit local PoC launcher, not production selectors. API processes never import their ML libraries. Missing/invalid runners fail closed. Every result records the loaded checkpoint hash and source revision; all thresholds remain unvalidated and all calibrated probabilities remain null. Approved-dataset benchmarking is deferred by the user; no accuracy/FPR claim is made.

| Field | CNNDetection GAN artifacts | LFCC-LCNN spectral/vocoder artifacts |
| --- | --- | --- |
| Identity / task | `cnn_gan_artifacts` / `synthetic_video` | `lfcc_lcnn_artifacts` / `audio_spoof` |
| Source | [authors' CNNDetection](https://github.com/PeterWang512/CNNDetection), revision `ea0b5622365e3a9cd31d1b54b6b5971131a839ab` | [official ASVspoof 2021 baselines](https://github.com/asvspoof-challenge/2021), revision `9b33f5eca887bd3bf629e3fb79428cd9bb7ac972`; DF model with LA shared libraries |
| Checkpoint | `blur_jpg_prob0.5.pth`, SHA256 `3533f3e58a3b82215f21197f2faf4e99b911ec42a4a6e2d7823e04d5f3fd245a` | `df_trained_network.pt`, SHA256 `7cee483813b118039cc3d63d24f744cf99303f5cfaffa5886eabecda91586b61` |
| Download source | Authors' Dropbox link in `download_public_assets.sh poc-artifacts` (from their weights script) | Official baseline download script's Dropbox fallback, pinned hash in the same installer |
| Training | ProGAN-generated versus real images with blur/JPEG augmentation, per upstream | ASVspoof 2019 LA training set used for the released 2021 DF baseline, per upstream README; no local retraining |
| License | Repository CC BY-NC-SA 4.0; no separate checkpoint license established | Shared implementation BSD-3-Clause; separate checkpoint licensing not established |
| Preprocessing | Official demo: uncropped RGB sampled JPEG, tensor/ImageNet mean/std, no resize | Mono 16kHz; official 20 LFCC plus delta/delta-delta, 320-sample Hamming frame, hop160, FFT1024, 0–4kHz filter range. Local window policy: consecutive 64600 samples, final repeat padding |
| Score | `sigmoid(synthetic_logit)` | `sigmoid(-bonafide_logit)`; raw stored logit retains bona-fide orientation |
| Aggregate / flag | Within-detector frame mean; mean>=0.5 flags the detector and returns above-rule sample times. Workflow findings honor this mean policy | Within-detector unweighted window mean; any window>=0.5 flags that window, even if the mean is lower |
| Limits | Not generator attribution or artifact localization; unknown generalization to DPS recordings | Not vocoder attribution or calibrated spoof probability; music/noise/non-speech and codecs confound screening; local segmentation policy requires evaluation |
| API setting / runner | `DEEPTRACE_GAN_ARTIFACT_COMMAND`; `cnn_artifacts.py` | `DEEPTRACE_VOCODER_ARTIFACT_COMMAND`; `lfcc_lcnn.py` |

LFCC compatibility is confined to its subprocess: legacy `torch.rfft` layout is computed with `torch.fft` and `view_as_real`; STFT explicitly requests the legacy real/imaginary layout. Tests compare FFT with a direct NumPy transform and upstream DCT with SciPy DCT. This is an API compatibility change, not a new learned frontend or checkpoint.

### SOFTNet micro-expression interval spotting

- Official [SoftNet-SpotME](https://github.com/genbing99/SoftNet-SpotME), revision `dd43d1e1d5ae471998ceb3be3177e2d9517c58fd`; [paper](https://arxiv.org/abs/2106.06489). The micro-expression CAS(ME)2 `s1.hdf5` release is copied locally as `CASME_micro_s1.hdf5`, SHA256 `5094d6ab73e11037a04a928b04551939b840416a12fbf5a8a07fe64386117ecd`. This is one released leave-one-subject-out fold, not a universal validated checkpoint or an ensemble.
- Training data: CAS(ME)2 micro-expression subset, upstream subject-fold training. No local retraining, label fitting or test-set threshold tuning. No top-level code/checkpoint license is stated in that repository; distribution/use rights need clarification before deployment. Upstream dlib 68-landmark asset SHA256 `fbdc2cb80eb9aa7a758672cbfdda32ba6300efe9b6e6c7a299ff7e736b11b92f`; its separate dataset-derived rights also require review.
- The runner extracts the authors' exact model-construction function from pinned source and loads numeric HDF5 weights by topology with `skip_mismatch=False`. Training optimizer construction is omitted. It also executes the authors' pinned feature extractor rather than substituting landmark motion for a neural prediction.
- Preprocessing: one stable reference face, 128x128 crop/JPEG/grayscale, native frame selection at30fps, TV-L1 flow at lag6, optical strain, nose-based global-motion removal, eye masking, eyebrow+mouth ROIs resampled42x42, per-channel min/max normalization. The paper's CAS(ME)2 micro window is k=6 at30fps. Lower source rates are rejected (29.97fps accepted with 29fps tolerance); no synthetic upsampling. Multiple/no faces or crop shifts over20% of reference face size abstain. At most the opening30s by default (CLI bounded1–120s).
- Output is an unbounded expression regression score, **not a fake score**. Match released code's 2*k smoothing/edge trim, adaptive `mean + .55*(max-mean)` threshold, minimum peak separation k, interval ±k. Correct the edge-trim offset when mapping peaks to source time. Constant scores yield no peaks. Raw regression thresholds/score range, coverage, checkpoint and candidate intervals persist in `ReviewCheck(technique="micro_expression")` and export to PDF technical details; they never create manipulation findings or change the officer assessment.
- Setting: `DEEPTRACE_MICRO_EXPRESSION_COMMAND`; runner `softnet.py`. The API rejects invalid technique/modality, validation claims, nonfinite measurements and invalid intervals. Unsupported input returns unavailable; crashes return error. There is no fabricated emotion/deception class.


### Coverage instrumentation and scene adaptation experiment (2026-11-11)

EfficientNet now observes the initial source-frame dlib call and records detection/alignment/scoring counts (`face_alignment_v1`). It returns exactly the upstream detections/crops; weights, preprocessing, score orientation, sampling and thresholds are unchanged. Fewer than half of attempted frames scored retains `LIMITED_FACE_COVERAGE`; zero crops still abstains. The workspace now preserves this limitation in its banner (v2), including while other detectors flag. No-face detection is not proof that a face is absent.

Community Forensics preprocessing was factored into `image_tensor()` without changing pixels. Offline checks compared exact tensors and logits with the prior path. Its shifted sigmoid now avoids overflow for extreme finite negative logits. The default release weights/boundary are unchanged.

`commfor.py --adaptation /path/to/adaptation.json` is an **opt-in research mode**. It replaces only the linear classifier using `head.safetensors`, strictly loaded against the existing ViT feature dimension. Config schema `commfor_head_adaptation_v1` binds base/head SHA-256, exact preprocessing version, development protocol fingerprint and selected raw-logit boundary. Revision suffix `+head-adaptation-v1` and notes identify the head; its base checkpoint remains recorded. Score semantics remain mean over per-frame `sigmoid(head_logit - development_boundary)`, uncalibrated, threshold 0.5; no detector fusion. No launch/config default enables it, and it is not operationally validated.

The Kaggle experiment uses the same selected FF++ c23/ComGenVid sources with terms and limitations as the banner experiment. Only genuine FF++ and labelled MSVD/Sora/Veo3 train this head; face-manipulated or audio-spoof labels are not converted into generated-scene labels. Frozen ViT GPU embeddings, equal class/source/video loss weighting, a predeclared epoch grid and per-source development FPR constraint are used. Source-group train/dev/test separation is frozen first, and previously seen smoke source groups are training-only. The final app banner is tested with all five independent checks on a separate holdout after the head/rule freeze. See [scene adaptation experiment](../backend/experiments/SCENE_ADAPTATION.md). **The completed small holdout showed improved scene results and fewer full-app false alarms, while full-app all-file accuracy remains below 85%; the candidate is not promoted.** See [verified validation results](VALIDATION_RESULTS.md): scene category 16/16, full app 46/49 decisive (eight incomplete excluded) or 46/57 all selected, and 1/27 observed genuine false alarms.
