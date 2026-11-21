# Model setup and adapter contract

For the complete five-classifier workstation profile with SOFTNet and supplementary checks, use [all-model team setup](../../docs/ALL_MODELS_SETUP.md). It includes the opt-in Compose profile, pinned extended dependencies, required asset checksums and readiness commands; model files and credentials remain outside Git.

### Development-selected face PoC rule

Set `DEEPTRACE_EFFICIENTNET_DECISION_RULE=ffpp_c23_kaggle_v1` in `backend/.env` for direct local API launches (or the root Compose environment for Docker), then restart the API. The explicit `scripts/run_local_poc.py` profile also opts into it. To retain the original rule in that launcher, pass `DEEPTRACE_EFFICIENTNET_DECISION_RULE=default_0_5` as an environment variable. Ordinary unset configuration retains 0.5. This changes only EfficientNet's any-frame rule to `0.9967585206031799`; it does not change audio or whole-frame screening thresholds, weights or inference preprocessing. Model/source/landmark provenance is checked and sampling must be 1 second with a 120-frame cap. Historical reports retain their original thresholds.

The threshold was selected on development data; it achieved 93.75% accuracy and 2.5% false-positive rate on the separate 80-video FF++ c23 subset. This is limited benchmark evidence, not fitted probability calibration, DPS operational acceptance or a guarantee for future uploads. See the [registry](../../docs/MODEL_REGISTRY.md#development-selected-face-poc-rule--november-11-2026) for provenance, counts and limitations.

Start here for model selection, environments, checkpoints, and the API protocol.
Real-checkpoint inference has not yet been validated.

| Modality | Default | Alternatives | Runner |
| --- | --- | --- | --- |
| Video | EfficientNet-B4 | Effort | `scripts/inference/efficientnetb4.py`, `effort.py` |
| Video, whole frame | Community Forensics frontier fine-tune (`DEEPTRACE_SCENE_COMMAND`) | none | `scripts/inference/commfor.py` |
| Audio | AASIST | AASIST-L, Nes2Net | `scripts/inference/aasist.py`, `nes2net.py` |

When `DEEPTRACE_SCENE_COMMAND` is set, the face model and the whole-frame model both run and are
reported as **separate** components (`face_manipulation`, `synthetic_video`). No max or average is
taken. Score semantics for every detector are in [`docs/MODEL_REGISTRY.md`](../../docs/MODEL_REGISTRY.md).
Weights: `Thermostatic/community-forensics-frontier-detector-2026-08`
at revision `16db135220b318d811b207db576d90368980b595` (MIT), saved as `models/commfor/frontier.safetensors`
with its `config.json`.

For the defaults, begin with [proposal candidate setup](#proposal-candidates-efficientnet-b4-and-aasistaasist-l).
The initial sections below cover the retained Effort and Nes2Net integrations.

The checked-in scripts in `scripts/inference/` execute the official architectures;
these are not simulated detectors. Model source is installed in ignored `vendor/`
by `bash scripts/download_models.sh`. The source revisions are pinned. Weights are
not bundled. Real-checkpoint inference has not yet been validated in this project.

## Environments

Keep the web service's Python environment separate from both inference environments.
The current web-service environment is Python 3.13; upstream ML requirements target
older Python/PyTorch versions and must not be installed into that environment.
Use separate Python 3.10 environments on the intended inference host. Install a
CPU or CUDA PyTorch/torchvision build appropriate to that host before other packages.

Effort needs its upstream `install.sh` dependencies (including dlib, transformers,
loralib, OpenCV, imutils and scikit-image). Review the version pins for the host;
the upstream shell script assumes CUDA 11.3 and is not a portable installer.
Nes2Net needs fairseq, librosa, NumPy and PyTorch. Follow the upstream speech README's
fairseq setup. Its requirements contain obsolete CUDA wheels and a machine-local
certifi path; do not blindly install that requirements file. Runtime compatibility
and exact dependency locks remain to be established on the inference host.

## Model assets

Download assets from the official sources linked below and record source, terms,
retrieval date and SHA-256 in your local manifest. Do not mix speech and singing
checkpoints or ASVspoof 5 and ASVspoof 19/21 architectures.

- Effort: the **FaceForensics++ CLIP-L/14 + Effort** checkpoint, the local Hugging Face
  CLIP ViT-L/14 directory (config and weights), and the **81-point** dlib landmark file.
  [Official Effort setup](https://github.com/YZY-stack/Effort-AIGI-Detection).
- Speech Nes2Net: the ASVspoof 19/21 **wav2vec2_Nes2Net_X** checkpoint and
  `xlsr2_300m.pt` frontend. Supported configuration: mean pooling, dilation 2,
  Nes ratios 8/8, SE ratio 1, two output logits.
  [Official speech setup and checkpoints](https://github.com/Liu-Tianchi/Nes2Net_ASVspoof_ITW).

Only load trusted upstream checkpoints. The classifier state dictionaries use
`weights_only=True` and strict loading. Fairseq's frontend loader uses its own
checkpoint deserialization. Missing keys or incompatible weights are errors;
there is no fallback to a randomly initialized detector.

## Configure the API

Set command templates in `.env`, replacing `/ABS` with your checkout and environment
paths. Quote paths containing spaces. Placeholders are substituted after command
splitting, so uploaded paths containing spaces stay in one argument.

```dotenv
DEEPTRACE_EFFORT_COMMAND='/ABS/deep_trace/backend/.venv-effort/bin/python /ABS/deep_trace/backend/scripts/inference/effort.py --repo /ABS/deep_trace/backend/vendor/Effort-AIGI-Detection --weights /ABS/deep_trace/backend/models/effort/ffpp.pth --clip /ABS/deep_trace/backend/models/effort/clip-vit-large-patch14 --landmarks /ABS/deep_trace/backend/models/effort/shape_predictor_81_face_landmarks.dat --frames {frames_dir} --device cpu'
DEEPTRACE_NES2NET_COMMAND='/ABS/deep_trace/backend/.venv-nes2net/bin/python /ABS/deep_trace/backend/scripts/inference/nes2net.py --repo /ABS/deep_trace/backend/vendor/Nes2Net_ASVspoof_ITW --weights /ABS/deep_trace/backend/models/nes2net/asvspoof21.pt --xlsr /ABS/deep_trace/backend/models/nes2net/xlsr2_300m.pt --audio {audio_path} --device cpu --test-mode 4s'
```

Run each command directly on public/synthetic media before enabling it in the API.
Successful stdout is one JSON object; diagnostics go to stderr and failures exit
nonzero. Use `--help` without installing ML dependencies to inspect the arguments.
The existing API calls these commands and includes checkpoint hashes, repository
revisions and coverage notes in reports. Models load once per request subprocess;
this favors isolation over throughput and is not a production serving design.

## Interpretation and coverage

Effort uses upstream face alignment and CLIP normalization, analyzing the largest
face per sampled frame. Unalignable faces are skipped. No faces produces an
unavailable result, not a real-media score. Frame filenames preserve timestamps
across skipped samples. The detector score is the uncalibrated fake-class softmax output.

Nes2Net resamples to mono 16 kHz. Default `4s` mode matches upstream first-four-second
cropping/repeat padding. It does **not** screen the entire recording. Set
`--test-mode full` for full-length evaluation, with substantially higher memory use.
The speech labels are spoof=0 and bona fide=1. The bridge applies softmax to both
logits and returns class 0; the upstream demo's class-1 raw logit is not a probability.
These scores and their arithmetic fusion remain uncalibrated. Benchmark the
integrated pipeline before drawing conclusions about detection performance.

## Proposal candidates: EfficientNet-B4 and AASIST/AASIST-L

The API now defaults to `DEEPTRACE_VIDEO_MODEL=efficientnetb4` and
`DEEPTRACE_AUDIO_MODEL=aasist`. Select `aasist-l` or `nes2net` for other audio
candidates and `effort` for the previous video integration. There is no automatic
fallback to a different model. AASIST-L requires both the selector and script
`--variant aasist-l`, with the matching official checkpoint.

`download_models.sh` pins the official AASIST and DeepfakeBench source as well.
For AASIST, use a separate environment with PyTorch, librosa, soundfile and the
upstream model requirements. For EfficientNet-B4, use PyTorch, efficientnet_pytorch,
OpenCV, dlib, PyYAML, tqdm, imutils and scikit-image plus upstream import dependencies.
Exact environment compatibility and real-checkpoint runs remain unvalidated.

Acquire the AASIST or AASIST-L checkpoint from https://github.com/clovaai/aasist,
and the trained EfficientNet-B4 detector from the weights linked by
https://github.com/SCLBD/DeepfakeBench. An ImageNet backbone is not a trained
FF++ detector. Use the 81-point landmark weights required by upstream preprocessing.
Record checkpoint origin, training split, license and hashes. DeepfakeBench uses
CC BY-NC 4.0; assess applicability before use outside this research PoC.

```dotenv
DEEPTRACE_AASIST_COMMAND='/ABS/deep_trace/backend/.venv-aasist/bin/python /ABS/deep_trace/backend/scripts/inference/aasist.py --repo /ABS/deep_trace/backend/vendor/aasist --weights /ABS/deep_trace/backend/models/aasist/AASIST.pth --audio {audio_path} --variant aasist --device cpu'
DEEPTRACE_EFFICIENTNET_COMMAND='/ABS/deep_trace/backend/.venv-models/bin/python /ABS/deep_trace/backend/scripts/inference/efficientnetb4.py --repo /ABS/deep_trace/backend/vendor/DeepfakeBench --weights /ABS/deep_trace/backend/models/efficientnetb4/effnb4_best.pth --landmarks /ABS/deep_trace/backend/models/efficientnetb4/shape_predictor_81_face_landmarks.dat --frames {frames_dir} --device cpu'
```

AASIST follows upstream first-64600-sample evaluation (4.0375 seconds), repeating
short clips; spoof is class 0. It does not assess the remainder of long recordings.
EfficientNet-B4 uses the official backbone and face alignment, 256px RGB crops,
mean/std 0.5 and fake class 1. It scores the largest alignable face per sampled
frame. Strict checkpoint loading rejects missing or incompatible model parameters.
These are operational bridges, not claims of reproduced benchmark performance.

## Adapter JSON contract

Commands are split before path substitution and run without a shell. Standard
output must contain one JSON object; diagnostics go to standard error. Failure
must exit nonzero. Both modalities accept optional `notes` (a list of strings).
`fake_probability` means a score from 0 (real/bona fide) to 1 (fake/spoof), not
an independently calibrated likelihood. Model scripts convert their respective
class order to this common convention.

Audio output:
```json
{"model_version":"repository revision","checkpoint":"filename#sha256=hash","fake_probability":0.61,"notes":[]}
```

Video output:
```json
{"model_version":"repository revision","checkpoint":"filename#sha256=hash","samples":[{"path":"frame_000001.jpg","fake_probability":0.73}],"notes":[]}
```

Frame names are one-based and preserve sample timing when faces are skipped.
An empty samples list means unavailable coverage. Audio scores have no localized
timestamps. Missing commands or invalid output produce unavailable/error results.

## Data and asset records

Record source URLs, retrieval dates, repository revisions, checkpoint filenames,
SHA-256 hashes, license terms, and training/evaluation splits in a local manifest.
Review Effort, speech Nes2Net, XLS-R and fairseq terms separately. Confirm Effort
licensing before use beyond this research PoC. Do not mix speech/singing models
or incompatible ASVspoof checkpoint configurations.

FaceForensics++ requires approved access; ASVspoof editions have distinct protocols.
Preserve official splits and review redistribution terms. Use approved public or
purpose-created synthetic media for initial development; sensitive agency media
requires separately agreed authorization and handling. The download script fetches
source code only and does not bypass dataset or checkpoint access requirements.
# Optional local PoC artifact analysis

From `backend/`, install sources and public checkpoints separately from datasets:

```sh
bash scripts/download_models.sh poc-artifacts
bash scripts/download_public_assets.sh poc-artifacts
.venv-models/bin/python -m pip uninstall -y opencv-python-headless
.venv-models/bin/python -m pip install -r requirements-poc-artifacts.txt
.venv-models/bin/python -m pip check
PORT=8001 .venv/bin/python scripts/run_local_poc.py
```

The optional runtime replaces base OpenCV with its contrib build for TV-L1 and adds the official LFCC-LCNN and SOFTNet dependencies. Do not install ML dependencies in the API environment. Existing base checkpoints are still required. Commands remain optional in portable settings; the launcher explicitly enables them locally. See `docs/MODEL_REGISTRY.md` for complete checkpoint hashes, preprocessing, licenses, score orientation and limits. No dataset is downloaded by these commands. Accuracy/FPR benchmarking is pending customer-approved labeled data.
