# Reproducing the all-model PoC profile

A fresh clone contains the runner code and model documentation, but not weights, upstream source checkouts, credentials, uploaded media, or local Docker images. The standard Docker profile configures three core classifiers. The explicit `docker-compose.all-models.yml` profile adds the complete CPU setup used on the project workstation; it does not change the standard profile's model defaults.

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

## Start the local stack

Docker with Compose **2.24.4 or newer**, Git, curl, and Python 3.9+ are required. The container uses Python 3.11. ARM64 Linux is the platform exercised on the project workstation and AWS sandbox. Other architectures need their own readiness and inference checks.

From the repository root:

```bash
bash scripts/start-local.sh
```

The script checks local files against [the asset manifest](../backend/model-assets.all.json), downloads missing files from the pinned sources, and verifies all nine asset hashes and five source revisions before building. It creates `.env` with random local account passwords and a JWT secret if the file is absent. If you already have a `.env`, the script keeps it and Compose uses its existing settings. The script builds the core image, layers on the additional models, and starts the all-model stack.

Open [DeepTrace](http://localhost:3000) and sign in with the employee or supervisor credentials in `.env`. Automatic sign-in is off. The frontend and API bind to loopback, and PostgreSQL has no published host port. Local cases and reports persist in Docker volumes.

## Download size and asset sources

The assets total **563,815,130 bytes (about 564 MB)**. Upstream source checkouts, Docker images, and Python dependencies are additional. Downloads come from the original release hosts, including the pinned Community Forensics release on Hugging Face. Check the [model registry](MODEL_REGISTRY.md) for license terms and limitations before redistributing any files.

```bash
# List asset sizes without downloading anything.
bash scripts/start-local.sh --plan

# Download and verify assets and create local credentials without starting Docker.
bash scripts/start-local.sh --prepare
```

An interrupted setup can be run again. If verification reports a changed source checkout or a checksum mismatch, inspect the reported path and move the affected file or checkout aside before retrying. The setup preserves source checkouts at other revisions and stops when verification fails.

## Check or stop the stack

```bash
docker compose -f docker-compose.yml -f docker-compose.all-models.yml ps
docker compose -f docker-compose.yml -f docker-compose.all-models.yml exec -T backend python scripts/verify_all_models.py --runtime
curl -fsS http://localhost:8000/health
docker compose -f docker-compose.yml -f docker-compose.all-models.yml stop
```

The runtime check verifies model dependencies, command configuration, and the SOFTNet checkpoint load. Review uploaded samples in the app to exercise inference and check coverage.

## AWS and team differences

The current AWS sandbox was seeded from the workstation's verified ARM64 images and checksum-verified files. Its separate deployment uses `deployment_mode=sandbox`, fresh credentials, authentication on, automatic login off, and an SSH tunnel for initial access. This file describes reproducible team setup, not a claim that a fresh clone contains those private runtime files or that the app has a public HTTPS endpoint.

For an AWS deployment, use explicit browser origins/API build URL and the organization's intended authentication, HTTPS endpoint, persistent-storage backup and network settings. Keep local automatic login disabled. Credentials, existing cases, private keys, checkpoint files, upstream checkouts and datasets stay outside Git. The independently evaluated scene adaptation remains opt-in research and is not promoted by this profile.
