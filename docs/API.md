# API contracts

Current behavior of the FastAPI service (`backend/deeptrace/main.py` mounts `api.router` and `workflow.routes.router`). Interactive schema: `http://localhost:8000/docs`. Architecture context: [ARCHITECTURE.md](ARCHITECTURE.md). Score semantics: [MODEL_REGISTRY.md](MODEL_REGISTRY.md).

## Conventions

- JSON only. Frontend clients: `frontend/lib/api.ts` (analyze + legacy report API) and `frontend/lib/workflow.ts` (workflow API, shared `send()` helper).
- **Auth:** `Authorization: Bearer <JWT>` on everything except `/health`, `/v1/auth/config`, `/v1/auth/login`, and the opt-in `/v1/auth/local-login`. When `DEEPTRACE_AUTH_ENABLED=false`, every request acts as `{"sub":"local-development","role":"analyst"}`.
- **Errors:** FastAPI shape `{"detail": "<message>"}`; request validation errors are 422 with `detail` as a list. Workflow service errors are `WorkflowError(status, detail)` mapped by `_call()` in `workflow/routes.py`. Clients treat 401 as `SESSION_EXPIRED`.
- **Not-found vs forbidden:** workflow reads return **404** when the caller cannot read the analysis (existence is not leaked); 403 is used for role-disallowed actions on readable analyses.
- **CORS:** origins from `DEEPTRACE_FRONTEND_ORIGINS`; methods GET/POST/PUT/PATCH/DELETE; headers `Authorization`, `Content-Type`.
- Roles: `analyst` (env investigator) ≡ `investigator` (directory user), `forensic_reviewer`, `supervisor`, `administrator`.

---

## Media analysis

### `POST /v1/analyze`

**Purpose.** Upload one audio/video file, run all configured detectors synchronously, persist results, return the advisory report.

**Request.** `multipart/form-data`, field `file`. The declared content type must be one of `audio/wav`, `audio/x-wav`, `audio/mpeg`, `audio/mp4`, `audio/x-m4a`, `audio/flac`, `video/mp4`, `video/quicktime`, `video/x-msvideo`, `video/avi`, `video/x-matroska`, `video/webm` (`media.ALLOWED_TYPES`).

**Response 200.** `AdvisoryReport` (`backend/deeptrace/schemas.py`, `report_version="0.3"`):

| Field | Meaning |
| --- | --- |
| `report_id` | Legacy report ID (key for `/v1/reports/*`) |
| `analysis_id` | Workflow analysis ID (key for `/v1/analyses/*`) |
| `media` | filename, `media_kind`, content type, size, SHA-256, duration, container, codecs, `extraction_warnings` |
| `components` | **Always three** `ComponentResult`s, in order: face manipulation, whole-frame synthetic video, audio spoof |
| `evidence_summary` | One entry per component: `task`, `detector_id`, `model_score`, `calibrated_probability`, `threshold`, `threshold_validated`, `status` |
| `overall_synthetic_confidence` | **Always `null`** for new reports (kept for stored v0.2 reports) |
| `anomalies` | Observations from components plus `METADATA_WARNING`. Old reports may retain `MODEL_DISAGREEMENT`. |
| `summary`, `recommended_action`, `methods`, `limitations`, `references`, `disclaimer`, `integrity` | Deterministic report text |
| `owner`, `reviewer`, `workflow_status` | Legacy store status (`draft` on creation) |

**Errors.** 401 (no/invalid token), 413 (exceeds `DEEPTRACE_MAX_UPLOAD_MB`, default 100), 415 (unsupported MIME), Video preparation failure now produces an incomplete report with error video components, while the audio adapter can still attempt the original file. A failing detector yields a component with `status="error"`. Storage failures are recorded in `processing` and limitations; the current response remains available to download, but history/workspace retrieval is not promised when storage is unavailable.

**Files.** `api.py::analyze`, `media.py`, `analyzers/`, `reporting.py`, `workflow/service.py::record_screening`, `report_store.py`.

### Detector result: `ComponentResult`

Each detector is reported **independently**. There is no aggregation across detectors. New reports no longer infer disagreement from numerical differences between unrelated task scores. Stored reports retaining `MODEL_DISAGREEMENT` remain readable.

| Field | Meaning |
| --- | --- |
| `component` | `video` or `audio` (both video detectors use `video`) |
| `task` | `face_manipulation` / `synthetic_video` / `audio_spoof` — the field that distinguishes detectors |
| `detector_id`, `detector_name`, `model_name`, `model_version`, `checkpoint` | Provenance (`checkpoint` = `filename#sha256=…`) |
| `status` | `functional` (scored), `not_applicable` (e.g. video detectors on audio), `unavailable` (unconfigured or no faces), `error` (runner failed), `stub` |
| `raw_score` | Model score in [0,1], **uncalibrated**. Video: unweighted mean over scored frames. Audio: file-level |
| `display_score`, `synthetic_confidence` | Aliases of `raw_score` (`synthetic_confidence` is deprecated) |
| `calibrated_probability` | Always `null` |
| `threshold`, `threshold_source`, `threshold_validated` | `0.5`, `default_model_decision_rule`, `false` |
| `thresholds`, `threshold_validation`, `operational_status` | Validated-threshold scaffolding; status is `threshold_not_validated` |
| `detector_status` | `score_only` / `not_available` / `error` |
| `aggregation_method`, `num_samples` | e.g. `mean_aligned_face_frame_score`, `mean_frame_score`, `file_level_model_output` |
| `samples[]` | `start_time`, `end_time`, `raw_score`, `raw_logits`, `predicted_class` (`possible_manipulation` if ≥ 0.5), `score_scope` (`sample`/`file`) |
| `timestamps_seconds` | Sample starts ≥ 0.5 (whole-frame detector: only when its mean ≥ 0.5) |
| `anomalies`, `notes`, `limitations`, `attribution` | Observations, runner notes (coverage, preprocessing), raw attribution payload |

The model-validator in `ComponentResult` fills aliases and derived fields; adapters set the semantic fields explicitly.

---

## Workflow API (case review)

All in `backend/deeptrace/workflow/routes.py` → `service.py`; schemas in `workflow/schemas.py`; client in `frontend/lib/workflow.ts`. Every route requires a bearer token.

| Method & path | Purpose | Who | Notable errors |
| --- | --- | --- | --- |
| `GET /v1/dashboard` | Four buckets of `AnalysisSummary` (max 8 each) | any | — |
| `GET /v1/queue` | Role-specific worklist | any | — |
| `GET /v1/search?q=` | Match filename, title, or comment text among visible analyses | any | 422 empty query |
| `GET /v1/analyses/{id}` | `AnalysisDetail`: media, `model_runs`, `findings`, `comments` | readable | 404 |
| `GET /v1/analyses/{id}/media` | Original upload (`FileResponse`) | readable | 404 |
| `POST /v1/analyses/{id}/findings/{fid}/reviews` | Append a disposition `{disposition, comment}` | owner investigator; forensic reviewer while `EXPERT_REVIEW_REQUESTED`; admin | 403, 404, 409 finalized, 422 |
| `POST /v1/analyses/{id}/comments` | `{body, finding_id?, parent_id?, timestamp_seconds?}`; `@mentions` parsed | readable | 404, 422 |
| `POST /v1/analyses/{id}/comments/{cid}/resolve?resolved=` | Resolve/unresolve thread | author, supervisor, admin | 403, 404 |
| `GET /v1/analyses/{id}/report` | `ReportOut`: `ai_original`, `current`, `revisions` | readable | 404 |
| `PUT /v1/analyses/{id}/report` | Save sections `{sections: {key: {text, origin}}}` → new `human_edit` revision if changed | owner investigator in editable status; supervisor may change **only** `reviewer_notes` during `SUPERVISOR_REVIEW` | 403, 409 |
| `GET /v1/analyses/{id}/report/diff` | Per-section AI vs current text | readable | 404 |
| `POST /v1/analyses/{id}/report/restore` | `{revision_id}` → new `restore` revision | owner investigator, editable | 403, 404, 409 |
| `POST /v1/analyses/{id}/report/submit` | → `SUPERVISOR_REVIEW`, assigns `DEEPTRACE_SUPERVISOR_USERNAME` | owner investigator | 403, 409 |
| `POST /v1/analyses/{id}/report/request-changes` | `{body}` → `CHANGES_REQUESTED` + comment | supervisor | 403, 409, 422 |
| `POST /v1/analyses/{id}/report/finalize` | → `FINALIZED` | supervisor | 403, 409 |
| `POST /v1/analyses/{id}/assistant` | `{question, history[≤12]}` → `{answer, citations, advisory_only, provider}` | readable | 404 |
| `GET /v1/audit?analysis_id=` | Up to 200 audit events | supervisor, admin; investigators see own analyses; reviewers 403 | 403 |
| `GET /v1/settings/models` | Configured models, decision threshold, preprocessing, limitation | any | — |
| `GET /v1/users` · `POST /v1/users` · `PATCH /v1/users/{username}` | Directory users (password ≥ 8 chars, PBKDF2) | administrator | 403 |

"Editable status" = `AI_SCREENING_COMPLETE`, `INVESTIGATOR_REVIEW`, `CHANGES_REQUESTED`. State transitions are diagrammed in [ARCHITECTURE.md](ARCHITECTURE.md#workflow-state-machine-workflow-db).

`GET /v1/settings/models` returns `video_model` / `video_configured` for the selected face detector, `audio_model` / `audio_configured` for the selected speech detector, and the additive fields `scene_model` (`community_forensics`) / `scene_configured` for the whole-frame detector. Scene fields default to `community_forensics` / `false` in the response schema. Configuration flags report whether the selected command is set; they do not establish checkpoint readiness or validated performance. No database schema changed.

### How detector results appear in the workflow API

`record_screening` converts each `ComponentResult` into:

- one **`model_runs[]`** entry: `modality`, `model_name`, `model_version`, `checkpoint`, `status`, `threshold` (= `DEEPTRACE_DECISION_THRESHOLD`), `raw_score` (the component's aggregate score), `calibrated_probability: null`, `preprocessing_version`, `notes`;
- zero or more **`findings[]`**: one per sample with `raw_score ≥ DEEPTRACE_DECISION_THRESHOLD` (`score_scope="sample"` for frames, `"file"` for audio). If no sample qualifies but the aggregate does, aggregate findings are created instead. Each finding has an `attribution` (`method`, `available`, `summary`, `metadata` — Grad-CAM heatmap/crop or audio occlusion windows).

Neither `model_runs` nor `findings` carry `detector_id`/`task`; distinguish face vs whole-frame by `model_name`. The whole-frame detector's frames ≥ threshold become findings even when its mean is below 0.5.

---

## Auth

| Method & path | Purpose | Notes |
| --- | --- | --- |
| `GET /v1/auth/config` | `{enabled, mode, domain, client_id, redirect_uri, local_auto_login}` | Public |
| `POST /v1/auth/login` | `{username, password}` → `{access_token, token_type, expires_in, role}` | 404 unless employee mode; 401 bad credentials; 503 if not configured |
| `POST /v1/auth/local-login` | No credentials in request → existing `LoginResponse` | Explicit local opt-in only; 404 when off/nonlocal deployment/nonemployee mode; 403 for nonloopback Host or unapproved/nonloopback Origin |
| `GET /health` | `{"status":"ok"}` | Used by Docker healthchecks |

## Legacy report API (`api.py` + `report_store.py`)

Still used by `/reports`, `/reports/[id]`, and `ReportView`. Keyed by `report_id`; separate status model (`draft → submitted → in_review → reviewed`) and separate comment/notebook tables.

| Method & path | Purpose | Who |
| --- | --- | --- |
| `GET /v1/reports` | Summaries (owner's; supervisors also see ones assigned to them) | any |
| `GET /v1/reports/{id}` | Stored `AdvisoryReport` | owner / assigned supervisor |
| `DELETE /v1/reports/{id}` (204) | Delete legacy report, linked workflow analysis, and media | owner or administrator |
| `POST /v1/reports/{id}/submit` | `draft → submitted` | role exactly `analyst` (directory `investigator` users get 403) |
| `POST /v1/reports/{id}/review/start` · `/review/complete` | `submitted → in_review → reviewed` | supervisor |
| `GET/POST /v1/reports/{id}/comments` | Shared comments (`body` ≤ 2000) | owner / assigned supervisor |
| `GET/PUT /v1/reports/{id}/notebook` | Private per-author notes (≤ 10000) | owner / assigned supervisor |
| `GET /v1/reports/{id}/media` | Original upload | owner / assigned supervisor |
| `GET/PATCH /v1/profile` | Display name and title | any |

Missing or inaccessible legacy reports return 404; invalid transitions 409.

## Runner JSON contract (internal)

Not HTTP, but a contract: `analyzers/` ↔ `scripts/inference/*`. Commands are `shlex`-split, then `{frames_dir}`, `{explain_dir}`, `{audio_path}` are substituted; no shell. Stdout = one JSON object, stderr = diagnostics, nonzero exit = failure.

```json
{"model_version": "...", "checkpoint": "file#sha256=...", "samples": [{"path": "frame_000001.jpg", "fake_probability": 0.73, "logits": [..], "attribution": {..}}], "notes": ["Scored N of M ..."]}
{"model_version": "...", "checkpoint": "file#sha256=...", "fake_probability": 0.61, "logits": [..], "attribution": {..}, "notes": []}
```

`fake_probability` is a model score in [0,1] (fake/spoof-oriented), not a calibrated probability. A `Scored N of M` note is parsed for face coverage.


## Extended local PoC (additive contracts)

`python scripts/run_local_poc.py` from the API environment opts into complete AASIST audio windows and supplementary measurements while preserving configured model selectors and authentication. It binds to 127.0.0.1; PORT defaults to 8000. Ordinary settings retain the original first-window policy and an unconfigured supplementary command.

- `ComponentResult.coverage` is optional: `{mode: "first"|"full", analyzed_seconds, duration_seconds, windows, complete}`. Window starts/ends exclude repeated padding. Full mode reports the unweighted mean of this detector's window scores and flags any window at or above the existing 0.5 development rule, even if the mean is lower. No cross-detector score is produced. This is a new unvalidated inference policy, not an operational threshold claim.
- `AdvisoryReport.review_checks` defaults to `[]`. Each entry contains technique, title, modality, status (`measured`, `unavailable`, `error`, `not_applicable`), method, measurements, timestamped intervals, limitations, method version, and `validated=false`. Measured means a descriptive statistic was computed; it does not mean a manipulation was detected. Seven techniques are represented: gan_frequency, blink, facial_motion, compression, mel_spectrogram, vocoder, background_noise.
- `AdvisoryReport.processing` defaults to `{}`. New responses include screening status, elapsed_seconds up to report persistence, and media_storage/workflow_storage/report_storage (`saved` or `unavailable`; internal pending states are replaced before return). No stored report is claimed when media retention fails. Storage failures do not erase the in-memory report response.
- `AnalysisDetail.review_checks` and `ModelRunOut.coverage` expose the same persisted data in the workspace. Existing JSON metadata columns carry these additions; no database migration or column change is required. Old rows return empty/absent values.
- Accepted uploads with absent/octet-stream MIME can use the six PoC extensions to determine the declared media category; unknown extensions remain rejected. Metadata decoding still records failures. JPEG extraction explicitly uses yuvj420p; sub-interval videos fall back to a single initial frame if the fps filter produces none.
- `DEEPTRACE_DEPLOYMENT_MODE=sandbox` refuses missing authentication configuration, wildcard browser origins, and the external media assistant. It does not replace network isolation, provisioning, TLS, or agency acceptance. Local mode remains available for synthetic functional tests.

Accuracy and false-positive acceptance work is deferred at the user's request pending the next dataset discussion. Public/synthetic functional inputs are not treated as an approved labeled validation set.
## Optional PoC artifact records

`/v1/settings/models` adds optional/default-empty `supplementary_methods[]` records (`task`, `model`, `configured`, `kind=detector|interval_spotter`). These describe configuration, not successful inference or validated capability. The Models page lists them within its existing method table.

`DEEPTRACE_GAN_ARTIFACT_COMMAND` and `DEEPTRACE_VOCODER_ARTIFACT_COMMAND` default to unset. When configured, `/v1/analyze` appends independent `ComponentResult` entries with detector IDs `cnn_gan_artifacts` (`synthetic_video`) and `lfcc_lcnn_artifacts` (`audio_spoof`). The portable response still has its original three components. Consumers must map by detector identity, not assume a fixed count. Existing task enums/DB columns are unchanged. New elevated observation codes are `ELEVATED_GAN_ARTIFACT_SCORE` and `ELEVATED_VOCODER_ARTIFACT_SCORE`.

`DEEPTRACE_MICRO_EXPRESSION_COMMAND` optionally appends `ReviewCheck` technique `micro_expression`, containing SOFTNet candidate intervals and raw regression measurements/provenance. It is not a synthetic-media score or finding. Check status remains `measured|unavailable|error|not_applicable`, validation remains false, and existing stored reports need no migration. Review-check ordering is not significant. Components, raw scores, samples, timestamps and coverage flow into existing ModelRun JSON; micro-expression intervals flow through review-check JSON to the workspace/PDF. No new route or authorization exception is introduced.

`processing.supplementary_status` records `completed|partial` separately from detector completion so an unavailable or failed supplementary method is visible without discarding usable detector results.

Whole-frame detectors with `aggregation_method=mean_frame_score` produce workflow review findings only when their within-detector mean reaches the declared threshold, matching their report rule. Per-sample values remain available even when no review finding is raised. Facial and windowed speech models retain their per-sample review rules. No cross-detector fusion is performed.

## Versioned face PoC decision rule (November 11, 2026)

`DEEPTRACE_EFFICIENTNET_DECISION_RULE` accepts `default_0_5` (portable default) or `ffpp_c23_kaggle_v1` (explicit local PoC profile). The latter uses the development-selected threshold `0.9967585206031799`, with `threshold_source=ffpp_c23_kaggle_v1_development_only_any_frame`. The matching checkpoint/source/landmark identifiers and benchmark sampling settings are required. A mismatch produces an error or configuration failure, not a fallback rule.

This is an opt-in behavior change, not a runner JSON or database-column change. The existing component `threshold` applies to frame classes, timestamps, observations and EfficientNet workflow findings. `DEEPTRACE_DECISION_THRESHOLD` no longer overrides an EfficientNet component's own declared rule; other workflow detectors retain their existing global-setting behavior. Face detection-level predicted class follows the any-frame rule while the reported raw score remains the within-detector frame mean. New ModelRun JSON metadata includes `threshold_source` and `threshold_validated`. Existing records remain unchanged and readable. No calibration, operational validation, new authorization route or score fusion is introduced.

`GET /v1/settings/models` adds defaulted fields `face_decision_rule: string` and `face_decision_threshold: number`; older clients can ignore them. The existing `decision_threshold` still describes the other workflow finding threshold, not a universal detector threshold. For the Effort selector the face rule remains `default_0_5`. Frontend types mirror the additions. Models, report technical details, workspace finding details and PDFs retain the threshold's full numeric precision rather than rounding the PoC threshold to 1.00. Recorded small-subset performance is documented in `MODEL_REGISTRY.md`; it is not a promise for new uploads or DPS acceptance.


### Additive face-coverage metadata (2026-11-11)

EfficientNet runner results can include `coverage` with `mode="face_alignment_v1"` and integer counts `frames_sampled`, `frames_with_detected_face`, `frames_without_detected_face`, `frames_with_unalignable_face`, `frames_scored`, plus `complete`. These describe sampled frames, not full-video or multi-face coverage. The initial dlib source-frame detection is observed without changing its outputs or the official alignment. Detected-but-unalignable faces are distinct from no detection; no detection does not establish absence of a face. Inconsistent counts fail closed. Zero scored crops remain `unavailable`, never automatically `not_applicable`.

`ComponentResult.coverage` and workflow `ModelRunOut.coverage` accept this shape or the existing first/full audio shape. Historical null/missing coverage is supported. The workflow adds optional `coverage_limited` (default false) in existing JSON run metadata; no DB column/migration or authorization change is required. New runs persist the `LIMITED_FACE_COVERAGE` warning. The investigator workspace now treats fewer than half of sampled frames scored as incomplete when nothing flags; flags remain visible alongside the coverage warning. Historical runner notes are retained/read for that warning. This aligns the workspace with the existing report overview's limited-coverage behavior and is versioned as workspace banner v2 in evaluation. Archived v1 evaluation remains replayable.


### Opt-in automatic login for a local workstation

`DEEPTRACE_LOCAL_AUTO_LOGIN=true` (default false) lets the loopback frontend obtain a normal expiring employee JWT from `POST /v1/auth/local-login`. Username/password stay on the backend; the token uses the configured employee username, preserving access to existing cases. Regular bearer validation, permissions, role separation and token lifetime are unchanged. Configuration refuses this flag with sandbox deployment, Cognito, disabled authentication, missing employee credentials or a JWT secret shorter than 32 characters.

The endpoint checks loopback Host and a configured loopback browser Origin. Run this opt-in only on a loopback-bound API: local Docker Compose now binds ports 3000/8000 to 127.0.0.1, and the local launcher already does so. Host/Origin checks are not a substitute for that network binding. Other deployments leave the flag off.

The frontend only requests this session on localhost/127.0.0.1/IPv6 loopback, when the server advertises the opt-in and no unexpired session exists. Valid manually selected accounts are retained. Automatic sessions renew after expiry/rejection. Explicit sign-out pauses automatic login for that tab, allowing another account to be chosen; a new browser tab/session can auto-login again. Failures show the existing sign-in/error flow; no fabricated token or client-side authorization bypass is used. Optional `AuthConfig.local_auto_login` is additive; no DB schema changes or stored-report changes.
