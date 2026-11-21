# DeepTrace

DeepTrace is a proof of concept for reviewing audio and video in public-safety investigations. An investigator uploads a recording, reviews findings, and submits a draft report to a supervisor. The supervisor can request changes or finalize the report. The case keeps report revisions and review history.

Each detector reports its own score and the parts of the recording it could assess. Investigators use those results to decide what to review. The software does not determine whether a recording is authentic.

## Run locally

Use Docker with Compose 2.24.4 or newer, Git, and Python 3.9 or newer for the setup scripts. The documented all-model profile was exercised on ARM64.

1. Follow the [all-model setup guide](docs/ALL_MODELS_SETUP.md) to obtain and verify the model files. The required assets total about 564 MB, plus source checkouts and container dependencies.
2. On a fresh checkout, copy `.env.all-models.example` to `.env`. Set the account passwords and JWT secret before starting the services.
3. Build and start the stack from the repository root.

```sh
docker build -t deeptrace-backend:core ./backend
docker compose -f docker-compose.yml -f docker-compose.all-models.yml build
docker compose -f docker-compose.yml -f docker-compose.all-models.yml up -d
curl -fsS http://localhost:8000/health
```

Open [DeepTrace](http://localhost:3000) and sign in with the investigator or supervisor account configured in `.env`. The [API reference](http://localhost:8000/docs) is available while the stack is running.

## Repository layout

| Path | Contents |
| --- | --- |
| `frontend/` | Next.js case workspace, review queue, and reporting UI |
| `backend/deeptrace/` | FastAPI endpoints, case workflow, persistence, and detector adapters |
| `backend/scripts/` | Model runners, setup, and verification scripts |
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

In the 57-file held-out experiment, the adapted research profile got 46 of 49 decisive results correct (93.9%). Eight results were incomplete. Across all 57 files, 46 were correct (80.7%). The all-model setup above uses the original scene checkpoint. See the [validation report](docs/VALIDATION_RESULTS.md) for the test splits, decision coverage, and limitations.

For implementation details, see [architecture](docs/ARCHITECTURE.md), [API contracts](docs/API.md), and the [model registry](docs/MODEL_REGISTRY.md).

Built by Silicon Peaks at the University of Southern Mississippi.
