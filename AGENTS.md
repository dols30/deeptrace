# DeepTrace — agent guide

Read this first. Specialized rules live in [`backend/AGENTS.md`](backend/AGENTS.md) (API, persistence, ML adapters) and [`frontend/AGENTS.md`](frontend/AGENTS.md) (Next.js, UI).

## Product purpose

DeepTrace is a proof-of-concept **advisory screening workspace** for public-safety investigators (the repository references Mississippi DPS). An investigator uploads audio or video; the backend runs independent pretrained detectors; the investigator dispositions each finding, writes the human sections of a report, and submits it to a supervisor who requests changes or finalizes.

Model output is a screening signal, never a determination. The product deliberately avoids "probability" language, fused scores, and authenticity claims. Preserve that posture in code, copy, and docs.

## Repository map

| Path | Owns |
| --- | --- |
| `backend/deeptrace/api.py` | `/v1/analyze`, auth login, legacy `/v1/reports/*`, profile routes |
| `backend/deeptrace/workflow/` | Case workflow: routes → `service.py` (state machine, authorization, report revisions, audit) |
| `backend/deeptrace/analyzers/` | Subprocess adapters that turn model-runner JSON into `ComponentResult` |
| `backend/deeptrace/schemas.py` | `ComponentResult` / `AdvisoryReport` — the detector result contract |
| `backend/deeptrace/reporting.py` | Builds the advisory report (summary, observations, limitations). No score fusion |
| `backend/deeptrace/ml/` | Finding derivation (`detectors.py`), attribution/explainer post-processing, case assistant, evaluation metrics. Never imports torch |
| `backend/deeptrace/db/` | SQLAlchemy models and engine/session lifecycle for the workflow DB |
| `backend/deeptrace/report_store.py` | Legacy raw-SQLite store (report JSON, comments, notebooks, profiles) |
| `backend/deeptrace/experimental/` | Isolated FakeSTormer/DeMamba adapters. Not imported by the API |
| `backend/scripts/inference/` | Model runner scripts executed in the separate model venv (torch lives here) |
| `backend/experiments/`, `backend/scripts/benchmark.py` | Benchmark/dataset tooling, not used at request time |
| `backend/alembic/` | Migration scaffolding (single revision that calls `create_all`) |
| `frontend/app/` | App Router pages. `globals.css` is the only stylesheet |
| `frontend/components/` | All UI; `workspace/` is the case-review workspace, `guide/` the guided tour |
| `frontend/lib/api.ts`, `frontend/lib/workflow.ts` | Typed API clients (legacy report API and workflow API respectively) |
| `docs/` | Cross-cutting docs (this system) plus attribution/explainability research notes |
| `backend/docs/` | Older backend notes (model setup, evaluation plan, roadmap). Partly superseded; see `docs/` |

Ignored, machine-local: `backend/models/` (checkpoints), `backend/vendor/` (pinned upstream source), `backend/.venv`, `backend/.venv-models`, `backend/data/`, `.env`.

## Technology stack (verified)

- **Frontend:** Next.js 16.3.4 (App Router, `next dev/build --webpack`, `output: 'standalone'`, `trailingSlash: true`), React 19.2, TypeScript 7 strict, Vitest 5 + Testing Library + jsdom. No UI kit, no CSS framework, no ESLint/Prettier.
- **API:** Python ≥3.11 (CI uses 3.12, Docker 3.11, local `.venv` 3.13), FastAPI 0.115, Pydantic Settings (`DEEPTRACE_` env prefix), SQLAlchemy 2, Alembic, PyJWT, psycopg 3. FFmpeg/ffprobe for media.
- **Model runtime (separate venv / Docker layer):** PyTorch 2.7.1, torchvision, timm, safetensors, dlib, OpenCV, librosa, efficientnet-pytorch (`backend/requirements-models-cpu.txt`). CPU by default.
- **Data:** SQLite locally, PostgreSQL 16 in Docker Compose. Media on local disk.
- **External services (optional):** AWS Cognito (auth mode `cognito`), Google Gemini (`DEEPTRACE_ASSISTANT_PROVIDER=gemini`).

## Architecture rules

Allowed dependency direction (details in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)):

```text
frontend ──HTTP/JSON──▶ api.py / workflow/routes.py ──▶ workflow/service.py ──▶ db/, report_store.py
                                   │                          │
                                   ▼                          ▼
                         analyzers/ ──subprocess──▶ scripts/inference/*   ml/ (pure Python post-processing)
```

- The **frontend** talks to the backend only over HTTP via `lib/api.ts` / `lib/workflow.ts`. No Next.js API routes. Frontend role checks are cosmetic; **authorization is enforced in the backend** (`workflow/access.py`, `workflow/service.py`, `api.py`).
- **Routes** stay thin: parse, call the service, map `WorkflowError` to HTTP. Business rules and state transitions belong in `workflow/service.py`.
- **API process never imports torch or model code.** Models run only inside `scripts/inference/*` via `analyzers/` subprocess calls. `ml/` is pure-Python post-processing.
- **Detectors are independent.** Each produces its own `ComponentResult`. Do not reintroduce cross-detector averaging/max/fusion without an explicit, validated design.
- **Persistence** happens in `workflow/service.py` (SQLAlchemy) and `report_store.py` (legacy SQLite). Analyzers and `ml/` do not write to storage.
- **External services** are isolated behind small classes (`auth.py` for Cognito JWKS, `ml/gemini_assistant.py`) and must degrade gracefully when unconfigured.

## Change discipline

Before modifying code:

1. Read this file.
2. Inspect the relevant implementation, not just its docs.
3. Trace the existing execution path end to end (e.g. upload → `analyze()` → analyzer → runner → `build_report` → `record_screening` → UI).
4. Read the routed documentation below.
5. Identify affected contracts: `ComponentResult`/`AdvisoryReport`, workflow schemas, runner JSON, DB tables, TS interfaces in `frontend/lib/`.
6. Inspect existing tests (`backend/tests/`, `frontend/components/*.test.tsx`).
7. Prefer extending existing abstractions (`VideoCommandAnalyzer`, `AudioCommandAnalyzer`, `send()` in `lib/workflow.ts`, `PageFrame`, existing CSS classes) over parallel systems.
8. Make the smallest coherent change.

## After-change verification

These are the commands this repository actually uses (from CI and READMEs). There is **no configured formatter, linter, or Python type checker** — do not claim to have run one.

| Check | Command |
| --- | --- |
| Backend tests | `cd backend && ./.venv/bin/python -m pytest` (CI: `python -m pytest`) |
| Backend syntax check | `cd backend && python -m compileall -q deeptrace scripts tests` |
| Frontend tests | `cd frontend && npm test` |
| Frontend type check | `cd frontend && npm run typecheck` |
| Frontend production build | `cd frontend && npm run build` |
| Model runtime readiness | `cd backend && .venv-models/bin/python scripts/verify_models.py` (needs checkpoints) |
| End-to-end smoke (running API) | `cd backend && .venv-models/bin/python scripts/smoke_pipeline.py` |
| Full stack | `docker compose up --build` (needs root `.env`) |
| Score-level benchmark metrics | `cd backend && python scripts/benchmark.py scores.csv` |

Backend tests do not need checkpoints. Adapter tests use tiny fake runner scripts, and API tests set commands to `None`. `Settings` reads `.env` from the working directory, so a local run from `backend/` also loads `backend/.env`. Report which checks you actually ran.

## Safety rules

- Do not silently change API contracts (`schemas.py`, `workflow/schemas.py`, TS interfaces). If you must, update both sides and [`docs/API.md`](docs/API.md).
- Do not silently change DB schemas. There are no incremental migrations; tables are created by `create_all`. Schema changes need an explicit migration plan.
- Do not replace or re-default production models unless explicitly requested. New detectors are opt-in.
- Do not change preprocessing, class-index orientation, score transforms, aggregation, or thresholds casually. They define what a score means. See [`docs/MODEL_REGISTRY.md`](docs/MODEL_REGISTRY.md).
- Never label a model score a "probability" or "confidence" in UI/report copy. `calibrated_probability` stays `null` until a fitted, versioned calibration exists.
- Do not claim tests passed unless you ran them.
- Do not expose or commit secrets, `.env`, credentials, checkpoints, datasets, or uploaded media.
- Preserve backward compatibility with stored reports (e.g. `synthetic_confidence`, `overall_synthetic_confidence` remain readable) unless intentionally migrating.
- Do not create duplicate abstractions when one exists (e.g. a second API client, a second detector base class, a second stylesheet).
- Keep the advisory disclaimers and limitations intact.

## Documentation routing

- Before architecture changes: read [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).
- Before model/ML changes: read [`docs/MODEL_REGISTRY.md`](docs/MODEL_REGISTRY.md) and [`backend/AGENTS.md`](backend/AGENTS.md).
- Before API changes: read [`docs/API.md`](docs/API.md).
- Before significant frontend/design changes: read [`docs/DESIGN_SYSTEM.md`](docs/DESIGN_SYSTEM.md) and [`frontend/AGENTS.md`](frontend/AGENTS.md).
- Model setup/environments: [`backend/docs/models.md`](backend/docs/models.md). Experimental detectors: [`docs/experimental_models.md`](docs/experimental_models.md). Attribution research: [`docs/model-inference-audit.md`](docs/model-inference-audit.md).

Project skills: `.cursor/skills/add-detector/` and `.cursor/skills/api-contract-change/`.
