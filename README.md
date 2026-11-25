# DeepTrace

DeepTrace is a proof of concept for reviewing audio and video in public-safety investigations. An investigator uploads a recording, reviews findings, and submits a draft report to a supervisor. The supervisor can request changes or finalize the report. The case keeps report revisions and review history.

Each detector reports its own score and the parts of the recording it could assess. Investigators use those results to decide what to review. The software does not determine whether a recording is authentic.

## Run locally

Install Docker with Compose 2.24.4 or newer, Git, curl, and Python 3.9 or newer. From the repository root, run:

```sh
bash scripts/start-local.sh
```

The first run downloads and verifies about 564 MB of model assets plus pinned source checkouts, creates local sign-in credentials in `.env`, and starts DeepTrace. Docker images and Python dependencies take additional space. Later runs reuse verified model files and the existing `.env`.

Open [DeepTrace](http://localhost:3000) and sign in with the employee or supervisor credentials in `.env`. See the [all-model setup guide](docs/ALL_MODELS_SETUP.md) for disk planning, supported platforms, and runtime checks.

## Repository layout

| Path | Contents |
| --- | --- |
| `frontend/` | Next.js case workspace, review queue, and reporting UI |
| `backend/deeptrace/` | FastAPI endpoints, case workflow, persistence, and detector adapters |
| `backend/scripts/` | Model runners, downloads, and verification |
| `scripts/start-local.sh` | Downloads the pinned assets and starts the local Docker stack |
| `backend/tests/` | API, workflow, and detector adapter tests |
| `docs/` | Architecture, API contracts, model configuration, and validation |
| `.github/workflows/` | GitHub Actions checks |

## Development checks

Run the backend tests in a Python 3.11 or newer environment with `requirements-dev.txt` installed. Run the frontend checks with Node 22.

```sh
(cd backend && python -m pytest tests -q)
(cd frontend && npm ci && npm test && npm run typecheck && npm run build)
```

## Validation

Only the matching labelled task is used for each model's individual accuracy. A generated video's whole-file label does not label its audio track as spoofed.

| Check | Matching test files | Accuracy | Observed FPR | Manipulation/spoof recall |
| --- | --- | ---: | ---: | ---: |
| EfficientNet-B4 face check | 10 genuine + 10 manipulated | **90.0% (18/20)** | 0/10 (0%) | 8/10 (80%) |
| Community Forensics, original scene head | 8 genuine + 8 generated | 87.5% (14/16) | 0/8 (0%) | 6/8 (75%) |
| Community Forensics, adapted scene head | Same 16 videos | **100% (16/16)** | 0/8 (0%) | 8/8 (100%) |
| AASIST, full-recording window profile | 9 genuine + 12 spoof utterances | **95.24% (20/21)** | 1/9 (11.11%) | 12/12 (100%) |
| LFCC-LCNN vocoder check | Same 21 utterances | 85.71% (18/21) | 1/9 (11.11%) | 10/12 (83.33%) |
| CNNDetection GAN-artifact check | 8 genuine + 8 generated videos | 50.0% (8/16) | 0/8 (0%) | 0/8 (0%) |
| SOFTNet and descriptive review measurements | Not evaluated as manipulation classifiers | Not established | Not established | Not established |

The adapted scene head was evaluated on a small held-out subset. The all-model setup uses the original scene checkpoint. See the [validation report](docs/VALIDATION_RESULTS.md) for test splits, coverage, and full results.

For implementation details, see [architecture](docs/ARCHITECTURE.md), [API contracts](docs/API.md), and the [model registry](docs/MODEL_REGISTRY.md).

Built by Silicon Peaks at the University of Southern Mississippi.
