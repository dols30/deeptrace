# Reproducing the all-model PoC profile

A fresh clone contains the runner code and model documentation, but not weights, upstream source checkouts, credentials, uploaded media, or local Docker images. The standard Docker profile (`DEEPTRACE_MODEL_PROFILE=core`) configures three core classifiers. `DEEPTRACE_MODEL_PROFILE=all-models` builds the `all-models` target of `backend/Dockerfile`, which adds the complete setup used on the project workstation; it does not change the core profile's model defaults.

## What the profile enables

| Check | Task | Configuration |
| --- | --- | --- |
| DeepfakeBench EfficientNet-B4 | Face manipulation | Existing `ffpp_c23_kaggle_v1` rule, any aligned frame >= 0.9967585206031799; one-second sampling, 120-frame cap |
| Community Forensics ViT-S/16 | Generated imagery | Original frontier checkpoint and release boundary; research adaptation head remains off |
| AASIST | Audio spoof screening | Full recording, non-overlapping windows, repeat-padding of final short window |
| CNNDetection ResNet-50 | Generated-image artifacts | Released blur/JPEG checkpoint; full sampled frames |
| LFCC-LCNN | Audio synthesis artifacts | Official ASVspoof 2021 DF weights, full-recording window policy |
| SOFTNet | Supplementary micro-expression intervals | CAS(ME)2 fold s1; opening 30 seconds; coverage/frame-rate requirements apply |
| Review measurements | Supplementary audio/video measurements | Existing `review_signals.py` runner; opening 30 seconds |

These are five independent classifiers plus supplementary checks. SOFTNet does not classify media as fake or infer deception. Unsupported media may cause individual checks to abstain; a silent video cannot exercise audio checks. Enabling a check is distinct from validating its accuracy. Model scores remain uncalibrated advisory signals, and no cross-detector score is produced. See [model semantics and limitations](MODEL_REGISTRY.md) and [validation results](VALIDATION_RESULTS.md).

## Plan disk space and acquire assets

Docker with Compose **2.24.4 or newer**, Git, and Python 3.9+ are needed for these setup commands. The container uses Python 3.11. ARM64 Linux is the platform exercised by the project workstation and AWS sandbox; other architectures need their own readiness/inference checks.

The exact required model/configuration/landmark files total **563,815,130 bytes (about 564 MB)**. Upstream Git clones and Docker/Python dependencies are additional and can occupy several GB. No validation datasets are required to run the app, and cloning this project does not download model files automatically. Inspect the size plan first:

```bash
cd backend
python3 scripts/verify_all_models.py --plan
```

Source URLs, commits, file sizes, and full SHA-256 values are recorded in [`model-assets.all.json`](../backend/model-assets.all.json). Read the source/checkpoint terms in [the registry](MODEL_REGISTRY.md); availability online does not itself grant redistribution rights. SOFTNet and its landmark asset have separately documented rights limitations. Share approved asset copies through the team's authorized storage, not Git.

After reviewing sizes and terms, install the pinned source repositories and public weights using the existing explicit download commands:

```bash
bash scripts/download_models.sh core
bash scripts/download_models.sh poc-artifacts
bash scripts/download_public_assets.sh models
bash scripts/download_public_assets.sh poc-artifacts
```

`core` installs AASIST and DeepfakeBench without the unused Effort/Nes2Net alternatives. `poc-artifacts` installs CNNDetection, ASVspoof 2021, and SOFTNet. Each source checkout receives a `.deeptrace-revision` marker so images can report the actual pinned revision after Git histories are excluded.

The public-weight script does **not** acquire Community Forensics. Obtain the team's approved original release files for `Thermostatic/community-forensics-frontier-detector-2026-08` revision `16db135220b318d811b207db576d90368980b595` and place them at:

```text
backend/models/commfor/frontier.safetensors
backend/models/commfor/config.json
```

Use the hashes in the asset catalog to verify these copies. An arbitrary Community Forensics checkpoint or the adapted research head is not equivalent. The 68-point landmark file is supplied by the pinned SOFTNet source checkout at `vendor/SoftNet-SpotME/Utils/shape_predictor_68_face_landmarks.dat`; it is separate from EfficientNet's 81-point landmark file.

Check the complete asset set before building:

```bash
python3 scripts/verify_all_models.py
cd ..
```

The verifier checks all nine asset hashes, all five source revisions, and modified tracked source files when Git metadata is available. It reports missing/mismatched inputs rather than substituting another model. It never downloads or analyzes media.

## Configure and build

The profile is a setting in the env file, not a separate compose file. On the Mac, set it in `.env` (start from [`.env.local.example`](../.env.local.example) on a fresh checkout, and preserve an existing `.env`). On the AWS host, set it in `.env.prod` ([AWS_DEPLOYMENT.md](AWS_DEPLOYMENT.md); use a g5.2xlarge or larger). Replace every credential placeholder; generate a JWT secret with `python3 -c 'import secrets; print(secrets.token_urlsafe(48))'`. Never commit credentials.

```dotenv
DEEPTRACE_MODEL_PROFILE=all-models
```

```bash
docker compose build
docker compose up -d
# AWS host: docker compose --env-file .env.prod build && docker compose --env-file .env.prod up -d
```

The `all-models` target extends the `core` stage in the same Dockerfile with pinned torchaudio/TensorFlow/Keras/pandas dependencies and OpenCV contrib (replacing the plain OpenCV package), the optional source files, and the profile's fixed settings: full-recording AASIST, the `ffpp_c23_kaggle_v1` face rule with one-second sampling and a 120-frame cap, the four extra runner commands, and per-runner thread caps. A plain `docker build ./backend` still produces the core image. Torch wheels come from the index in `DEEPTRACE_TORCH_INDEX` (`cpu` by default, `cu126` on the GPU host), and the same value is used for torchaudio. Allow several GB of free Docker disk (`docker system df`, `docker builder prune`).

On the GPU host the profile runs on CUDA like the core detectors. GPU inference can differ from CPU in the last floating-point digits, so scores near a decision threshold may land differently; reported thresholds and decision rules were set on CPU runs. See [MODEL_ORCHESTRATION.md](MODEL_ORCHESTRATION.md).

Sign in at http://localhost:3000 using your newly configured employee or supervisor credentials. Keep automatic sign-in off (`DEEPTRACE_LOCAL_AUTO_LOGIN=false`) for this profile. API access remains authenticated, frontend/API host ports remain loopback-only, and PostgreSQL has no published host port. Both workflow and legacy report/media stores remain persistent Docker volumes. All-model configuration does not erase history.

Run readiness checks inside the configured model container:

```bash
docker compose ps
docker compose exec -T backend python scripts/verify_all_models.py --runtime
curl -fsS http://localhost:8000/health
```

The runtime check confirms dependency imports, configured commands, coverage/rule settings, and strict SOFTNet weight loading. It does not analyze demo files or establish accuracy. Check new uploads in the app and inspect every component's coverage and limitations. Docker image rebuilds are needed after changing packaged weights, sources or dependencies.

## AWS and team differences

The current AWS sandbox was seeded from the workstation's verified ARM64 images and checksum-verified files. Its separate deployment uses `deployment_mode=sandbox`, fresh credentials, authentication on, automatic login off, and an SSH tunnel for initial access. This file describes reproducible team setup, not a claim that a fresh clone contains those private runtime files or that the app has a public HTTPS endpoint.

For an AWS deployment, use explicit browser origins/API build URL and the organization's intended authentication, HTTPS endpoint, persistent-storage backup and network settings. Keep local automatic login disabled. Credentials, existing cases, private keys, checkpoint files, upstream checkouts and datasets stay outside Git. The independently evaluated scene adaptation remains opt-in research and is not promoted by this profile.
