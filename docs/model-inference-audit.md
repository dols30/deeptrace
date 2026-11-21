# Model inference audit

Audit date: 2026-09-30. This document records the inference paths DeepTrace actually runs. It is the input to the attribution plans. Shapes below were measured by the read-only probes, not copied from an EfficientNet or AASIST tutorial.

## Environments

| Role | Path | Python | What it loads |
| --- | --- | --- | --- |
| API | `backend/.venv` | 3.13.9 | FastAPI, no PyTorch |
| Model runners | `backend/.venv-models` | 3.11.15 | torch 2.7.1, efficientnet_pytorch, OpenCV 4.10.0, dlib 19.24.6, librosa 0.10.2.post1 |

`backend/docs/models.md` still describes a Python 3.10 inference environment. The checkout that produced this audit uses Python 3.11.15 in `.venv-models`. Captum is not installed there.

Inference is a subprocess. `POST /v1/analyze` in `backend/deeptrace/api.py` never imports `EfficientNetB4` or AASIST `Model`. Each request starts the command in `DEEPTRACE_EFFICIENTNET_COMMAND` or `DEEPTRACE_AASIST_COMMAND`, reads one JSON object from stdout, and builds an `AdvisoryReport`.

## Video path

```text
uploaded video
  -> ffmpeg fps=1/{interval}, max 120 JPEGs, -q:v 2     media.prepare_video
  -> frame_000001.jpg ...
  -> dlib frontal detector, largest face
  -> 81-point landmarks, five-point similarity warp to 256x256
  -> second dlib detect on the aligned crop (drop the frame if it fails)
  -> RGB / 255, then (x - 0.5) / 0.5
  -> EfficientNetB4
  -> logits (1, 2)
  -> softmax class 1 = fake-class screening score
  -> unweighted mean of scored frames = video screening score
```

### Sources

| Item | Value |
| --- | --- |
| Repository | https://github.com/SCLBD/DeepfakeBench |
| Pinned revision | `f188b1c105465e2e5377eb536a95022ae0e4522d` (`backend/scripts/inference/common.py`, `backend/scripts/download_models.sh`) |
| License | CC BY-NC 4.0. Text in `backend/vendor/DeepfakeBench/LICENSE`. Copyright 2023, CUHK(SZ). Non-commercial terms apply to the vendored source. |
| Backbone library | `efficientnet_pytorch`  (Apache-2.0). Installed copy: `backend/.venv-models/lib/python3.11/site-packages/efficientnet_pytorch/model.py`. DeepfakeBench's own license file lists efficientnet-pytorch 0.7.1 as Apache-2.0. |
| Paper for the benchmark | Yan et al., DeepfakeBench, arXiv:2307.01426, https://arxiv.org/abs/2307.01426 |
| Paper for the architecture | Tan and Le, EfficientNet, ICML 2019, https://arxiv.org/abs/1905.11946 |
| Runner | `backend/scripts/inference/efficientnetb4.py`, `main` |
| API adapter | `EfficientNetVideoAnalyzer` in `backend/deeptrace/analyzers/video.py` |
| Network class | `EfficientNetB4` in `backend/vendor/DeepfakeBench/training/networks/efficientnetb4.py` |
| Detector class (training/eval wrapper, not called by DeepTrace) | `EfficientDetector` in `backend/vendor/DeepfakeBench/training/detectors/efficientnetb4_detector.py` |
| Training config | `backend/vendor/DeepfakeBench/training/config/detector/efficientnetb4.yaml` |
| Face function | `extract_aligned_face_dlib` in `backend/vendor/DeepfakeBench/preprocessing/preprocess.py` |
| Checkpoint | `backend/models/efficientnetb4/effnb4_best.pth` |
| Checkpoint URL | https://github.com/SCLBD/DeepfakeBench/releases/download/v1.0.1/effnb4_best.pth |
| SHA-256 | `74cbd82d7be1bf5e6adec717824274a95b4509b02e1e78401608d32b3cbeaf0f` |
| Landmarks | `backend/models/efficientnetb4/shape_predictor_81_face_landmarks.dat` |
| Landmarks URL | https://github.com/SCLBD/DeepfakeBench/releases/download/v1.0.0/shape_predictor_81_face_landmarks.dat |
| Landmarks SHA-256 | `8cae4375589dd915d9a0a881101bed1bbb4e9887e35e63b024388f1ca25ff869` |

The ImageNet file named in the training YAML (`efficientnet-b4-6ed6700e.pth`, `pretrained:`) is an initialization checkpoint. DeepTrace does not load it. `efficientnetb4.py` constructs `EfficientNet.from_name('efficientnet-b4')` with `pretrained=False`, then `load_state_dict(..., strict=True)` on `effnb4_best.pth` after stripping `module.` and `backbone.` prefixes. The probe completed that strict load on 2026-09-30.

### Preprocessing

`prepare_video` (`backend/deeptrace/media.py`) writes JPEGs with ffmpeg:

- `fps=1/{DEEPTRACE_FRAME_INTERVAL_SECONDS}` (default 1.0, so 1 frame per second)
- `-frames:v` capped by `DEEPTRACE_MAX_FRAMES` (default 120)
- quality `-q:v 2`
- names `frame_%06d.jpg` (one-based)

The runner reads those JPEGs with `cv2.imread`. For each image, `extract_aligned_face_dlib(..., res=256)`:

1. Converts BGR to RGB and runs `dlib.get_frontal_face_detector`.
2. Keeps the largest rectangle.
3. Reads five landmarks from the 81-point predictor via `get_keypts`: parts 37, 44, 30, 49, and 55 (left eye, right eye, nose, left mouth, right mouth in that predictor's indexing).
4. Estimates a scikit-image `SimilarityTransform` from those points onto a 112-pixel template, scaled to `outsize=(256, 256)` with `scale=1.3`.
5. Warps with the 2x3 matrix `M = tform.params[0:2, :]`.
6. Runs dlib again on the aligned crop. If that second detect fails, the function returns `(None, None, None)` and the runner skips the frame.

`M` and the original-frame landmarks are discarded. The runner keeps only the 256x256 BGR crop. That is the coordinate gap attribution has to close. See `docs/video-attribution-plan.md`.

Normalization matches the detector YAML (`mean: [0.5, 0.5, 0.5]`, `std: [0.5, 0.5, 0.5]`):

```text
RGB uint8 -> float32 / 255 -> (pixel - 0.5) / 0.5 -> CHW -> batch (1, 3, 256, 256)
```

The YAML also sets `resolution: 256`. Stock EfficientNet-B4 was designed for 380x380 (Tan and Le). This detector is trained and run at 256.

DeepfakeBench replaces `_conv_stem` with `Conv2d(3, 48, kernel_size=3, stride=2, bias=False)` and default padding 0. A stock EfficientNet stem is padded. The probe measured stem output `(1, 48, 127, 127)` for a 256 input, which is the padding-0 result: `floor((256 - 3) / 2) + 1 = 127`. The released checkpoint matches this modified stem (strict load). Attribution must use this network, not a padded ImageNet EfficientNet-B4.

### What the number is

`EfficientNetB4.forward` returns two logits from `last_layer = Linear(1792, 2)`.

DeepfakeBench `label_dict` in `training/config/train_config.yaml` maps real datasets to 0 and fake datasets to 1 (`FF-real: 0`, `FF-DF: 1`, and the same pattern for the other listed sets). `EfficientDetector.forward` publishes `torch.softmax(pred, dim=1)[:, 1]` as `prob`.

DeepTrace does the same conversion in `efficientnetb4.py`:

```text
fake_probability = softmax(logits)[0, 1]
```

`common.probability` requires a finite value in `[0, 1]`. The stored field is `ComponentResult.synthetic_confidence`. It is an uncalibrated softmax, not a calibrated probability. `backend/deeptrace/reporting.py` says this in `LIMITATIONS`. The UI still labels it "COMBINED MODEL CONFIDENCE" and "FAKE / SPOOF SCORE" (`frontend/components/report.tsx`) and formats it with `formatConfidence` (`frontend/lib/api.ts`).

Frame scores are combined by an unweighted mean in `VideoCommandAnalyzer.analyze`. A frame at or above 0.5 appends `ELEVATED_FRAME_SCORE` and a timestamp of `(frame_index) * interval`, where `frame_index` comes from `frame_(\d+).jpg` minus one. If fewer than half of the attempted frames are scored, the adapter adds `LIMITED_FACE_COVERAGE`. An empty sample list becomes status `unavailable`, not a real-media score.

`ModelSample.end_time` is `start + interval`. The model saw one JPEG, not a one-second clip. The timestamp is the sample time of that JPEG.

The forward pass in the runner is inside `torch.inference_mode()`. Gradients do not flow on that path. The probe, run outside `inference_mode`, showed that a backward from logit index 1 does reach the feature map and the input pixels. See the measured shapes below.

### Measured video shapes

Command, 2026-09-30, CPU, strict checkpoint load:

```text
backend/.venv-models/bin/python backend/scripts/dev/inspect_efficientnetb4.py \
  --repo backend/vendor/DeepfakeBench \
  --weights backend/models/efficientnetb4/effnb4_best.pth
```

| Tensor | Shape |
| --- | --- |
| Model input | `(1, 3, 256, 256)` |
| `efficientnet._conv_stem` | `(1, 48, 127, 127)` |
| `efficientnet._blocks.0` | `(1, 24, 127, 127)` |
| `efficientnet._blocks.9` | `(1, 56, 32, 32)` |
| `efficientnet._blocks.21` | `(1, 160, 16, 16)` |
| `efficientnet._blocks.31` (last of 32) | `(1, 448, 8, 8)` |
| `efficientnet._conv_head` | `(1, 1792, 8, 8)` |
| `EfficientNetB4.features` (post-Swish) | `(1, 1792, 8, 8)` |
| Logits | `(1, 2)` |

`last_layer` is `Linear(1792, 2)`. Gradients from logit 1 reached `features` and the input tensor.

### Disagreement with DeepfakeBench's own sampling

The detector YAML sets `frame_num: {'train': 32, 'test': 32}`. DeepTrace samples 1 fps up to 120 JPEGs and then lets the runner align faces. Video scores are therefore not the benchmark's 32-frame protocol. The checkpoint and the face warp match DeepfakeBench. The frame schedule does not.

## Audio path

```text
uploaded audio, or mono 16 kHz PCM extracted from video
  -> librosa.load(sr=16000, mono=True), ffmpeg f32le fallback
  -> data_utils.pad to 64600 samples (truncate or repeat-tile)
  -> AASIST Model.forward
  -> logits (1, 2)
  -> softmax class 0 = spoof screening score
  -> that single number is the recording screening score
```

There is no second window and no aggregation across the rest of a long file.

### Sources

| Item | Value |
| --- | --- |
| Repository | https://github.com/clovaai/aasist |
| Pinned revision | `a04c9863f63d44471dde8a6abcb3b082b07cd1d1` |
| License | MIT. Copyright 2021-present NAVER Corp. Text in `backend/vendor/aasist/models/AASIST.py` and `backend/vendor/aasist/LICENSE`. |
| Paper | Jung et al., AASIST, ICASSP 2022, https://arxiv.org/abs/2110.01200 |
| Model class | `Model` in `backend/vendor/aasist/models/AASIST.py` |
| Config | `backend/vendor/aasist/config/AASIST.conf` (`architecture` is still `"AASIST"`) |
| Pad | `pad` in `backend/vendor/aasist/data_utils.py` |
| Official eval score | `produce_evaluation_file` in `backend/vendor/aasist/main.py` |
| Runner | `backend/scripts/inference/aasist.py`, `main` |
| API adapter | `AASISTAudioAnalyzer` in `backend/deeptrace/analyzers/audio.py` |
| Checkpoint | `backend/models/aasist/AASIST.pth` |
| Checkpoint URL | Hugging Face `SpeechAntiSpoofingBenchmarks/AASIST` at revision `16774d458d86d2a021ae31646c1bf66a5331b53e`, fetched by `backend/scripts/download_public_assets.sh` |
| SHA-256 | `51d2d9cf0738172f61e2a384ec50a54a55363240f67c971ed55a92435bc1a1c0` |
| Training data named by the upstream README | ASVspoof 2019 LA, https://datashare.ed.ac.uk/handle/10283/3336 |

AASIST-L is the same `Model` class with `config/AASIST-L.conf` and a different checkpoint. It is not the default (`DEEPTRACE_AUDIO_MODEL=aasist`).

### Preprocessing

- Sample rate: 16 kHz mono. Video uploads are extracted in `prepare_video` as PCM s16le, 1 channel, 16000 Hz. The runner decodes again with librosa at 16 kHz, or ffmpeg `pcm_f32le` if librosa fails.
- No waveform mean/std normalization in the runner. Scale is whatever the decoder emits. The network's batch-norm and SELU sit after the sinc frontend.
- Duration: `pad(x, max_len=64600)`. Longer audio becomes `x[:64600]`. Shorter audio is repeated with `np.tile` until 64600 samples. 64600 / 16000 = 4.0375 seconds.
- Training uses `pad_random`, which crops a random 64600-sample span when the file is longer. Inference uses `pad`, which always keeps the start. Those are different windows.
- `nb_samp` in `AASIST.conf` is 64600. `first_conv` is 128. `CONV.__init__` forces an even kernel to the next odd length, so the sinc kernel is 129. The probe's `conv_time` length 64472 matches `64600 - 129 + 1`.

### What the number is

`Model.forward` returns `(last_hidden, output)` and `output` is `out_layer`, `Linear(160, 2)`.

Upstream labels in `genSpoof_list`: bonafide = 1, spoof = 0.

Upstream evaluation stores the raw bonafide logit:

```text
batch_score = batch_out[:, 1]
```

DeepTrace stores the spoof-class softmax:

```text
score = softmax(logits)[0, 0]
```

Both conventions can rank the same pair of logits, but they are not the same number. Occlusion and any later gradient method that talks about "the screening score" must use `softmax[:, 0]`, because that is the number on the report. A delta computed on the bonafide logit would not match the sentence "masking changed the model screening score by 0.17."

The runner does this inside `torch.inference_mode()` and `model.eval()`. The official eval loop uses `torch.no_grad()`. Either one blocks autograd. The probe, outside `inference_mode`, showed that a backward from logit 0 reaches the waveform.

The adapter copies `fake_probability` into `synthetic_confidence`. Audio `timestamps_seconds` stays empty. `ModelSample` is one file-scoped row whose `end_time` is `metadata.duration_seconds`. That end time is the whole file, including audio the model never saw. The runner note already says the score does not describe the remainder.

A score at or above 0.5 adds `ELEVATED_SPOOF_SCORE`. The threshold is provisional. It is not an equal-error-rate operating point measured for this deployment.

### Measured audio shapes

Command, 2026-09-30, CPU, strict checkpoint load, random `(1, 64600)` input, `model.eval()`:

```text
backend/.venv-models/bin/python backend/scripts/dev/inspect_aasist.py \
  --repo backend/vendor/aasist \
  --weights backend/models/aasist/AASIST.pth
```

| Stage | Module | Shape |
| --- | --- | --- |
| Waveform | input | `(1, 64600)` |
| Sinc frontend | `conv_time` | `(1, 70, 64472)` |
| After abs max-pool `(3, 3)` and BN | `first_bn` | `(1, 1, 23, 21490)` |
| Residual encoder | `encoder` | `(1, 64, 23, 29)` |
| Spectral graph attention | `GAT_layer_S` | `(1, 23, 64)` |
| Temporal graph attention | `GAT_layer_T` | `(1, 29, 64)` |
| Spectral pool, ratio 0.5 | `pool_S` | `(1, 11, 64)` |
| Temporal pool, ratio 0.7 | `pool_T` | `(1, 20, 64)` |
| Heterogeneous GAT, branch 1 | `HtrgGAT_layer_ST11` | temporal `(1, 20, 32)`, spectral `(1, 11, 32)`, master `(1, 1, 32)` |
| After heterogeneous pool | `pool_hT1`, `pool_hS1` | `(1, 10, 32)`, `(1, 5, 32)` |
| Readout | `last_hidden` | `(1, 160)` |
| Classifier | `out_layer` | `(1, 2)` |

`pos_S` is `(1, 23, 64)`, which fixes the spectral node count at 23 before pooling. Attention maps exist inside `_derive_att_map` and are not returned by `forward`. Measured map shapes are in `docs/aasist-attribution-plan.md`.

Node counts after `GraphPool` follow `max(int(n * k), 1)` and matched these shapes. Which nodes survive is input-dependent. The count is not.

## How a report is assembled

`build_report` (`backend/deeptrace/reporting.py`):

- Both modalities functional: `video * visual_weight + audio * (1 - visual_weight)` with default `visual_weight` 0.5.
- Otherwise: mean of the functional scores, or null if none exist.
- Absolute difference of at least 0.25 adds `MODEL_DISAGREEMENT`.
- `calibrated_probability` on the newer `DetectionResult` type is always null today. Nothing in the runners fits a calibrator.

`record_screening` stores a workflow row. `save_report` stores the advisory JSON. Component notes, checkpoint ids (`filename#sha256=`), and model revisions are already on the report.

## What attribution code exists, and what it does not do

`backend/deeptrace/ml/attribution.py` defines `grad_cam` (channel-weighted sum, ReLU, peak normalization) and `GradCAMVideoAttribution`. `EfficientNetB4Detector.explain` calls it only if `detection.metadata` already contains `feature_maps` and `gradients`. `detection_from_component` never puts those tensors in metadata. The checkpoint runner does not emit them. The helper therefore returns `available: false`.

`AASISTAudioAttribution` normalizes `temporal_relevance`, `spectral_relevance`, or `graph_attention` if the adapter JSON contains them. `aasist.py` does not emit those keys. `normalize_series` also takes the absolute value, so a signed score delta would be discarded if it were passed through that helper unchanged.

`AudioCommandAnalyzer` will copy those three keys when present. The video runner has no equivalent field. The frontend `ComponentResult` type in `frontend/lib/api.ts` does not include `samples` or `attribution`.

So the product can store a screening score, a checkpoint hash, and a model revision. It cannot yet show a map that was computed from these weights.

## Implications

- Explainers belong in the model virtualenv, next to the runners, and must return JSON. The API process stays free of PyTorch.
- Grad-CAM and integrated gradients need a forward that is not wrapped in `inference_mode`.
- The video overlay has to carry the similarity matrix `M`. The current runner throws it away.
- The audio timeline that the model actually scored is `[0, 4.0375)` seconds of the decoded waveform, or a tiled short clip. A one-minute bar of attribution would describe audio the network did not receive.
- The displayed quantity is a softmax. Call it a model screening score until a calibration model exists.
- DeepfakeBench's CC BY-NC 4.0 license covers the vendored detector source. Attribution code should stay in DeepTrace wrappers and call the loaded module, rather than forking the vendor package into a new product tree.
