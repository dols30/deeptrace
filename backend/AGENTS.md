# Backend agent rules

Applies to `backend/`. Read the root [`AGENTS.md`](../AGENTS.md) first. Contracts: [`docs/API.md`](../docs/API.md). Models: [`docs/MODEL_REGISTRY.md`](../docs/MODEL_REGISTRY.md).

## Environments

- `.venv` — API only (FastAPI, SQLAlchemy). **No torch.** Tests run here: `./.venv/bin/python -m pytest`.
- `.venv-models` — model runners (`requirements-models-cpu.txt`). Never install ML packages into `.venv`, and never import runner code from `deeptrace/`.
- FakeSTormer needs its own CUDA environment (`requirements-fakestormer.txt`).
- Settings come from `deeptrace/config.py` (`DEEPTRACE_*`). Add new settings there with safe defaults, and document them in `.env.example` without real values.

## API and workflow

- Routes stay thin. Put rules, state transitions and authorization in `workflow/service.py` / `workflow/access.py`, and raise `WorkflowError(status, detail)`.
- Unreadable analyses return 404, not 403.
- Every state-changing workflow action writes an audit event (`_audit`).
- `Report.ai_original` is never modified. Edits append `ReportRevision`, and dispositions append `FindingReview`.
- Two stores exist (`report_store.py` legacy SQLite, `db/` workflow). Do not add features to the legacy store. Do not remove it without migrating `/reports` UI and `DELETE /v1/reports/{id}`.
- There are no incremental migrations (`create_all` only). Adding or renaming columns requires an Alembic revision with real `op.*` operations plus a note in the PR.

## Detector adapters and runners

- One runner script per model in `scripts/inference/`, wrapped by `common.run()`. Stdout is one JSON object, stderr is for diagnostics, and failure exits nonzero.
- One adapter class per model in `analyzers/`, subclassing `VideoCommandAnalyzer` or `AudioCommandAnalyzer`. Set `model_name`, `command_setting`, `detector_id`, `task`, `aggregation_method`.
- Adapters fail closed. Missing command → `unavailable`; bad output/exception → `error` with a truncated stderr diagnostic. Never return a placeholder score or fall back to another model.
- Commands are split with `shlex` and run without a shell. Keep placeholders as `{frames_dir}`, `{explain_dir}`, `{audio_path}`.
- Load checkpoints with `weights_only=True` and `strict=True`. Report `checkpoint_id()` (filename + SHA-256) and the upstream revision.

## ML semantics: change only on purpose

These define what a number means. Changing any of them is a model change and must be called out, tested, and reflected in `docs/MODEL_REGISTRY.md`:

- preprocessing (face detector, alignment, crop/resize, normalization, sample rate, 64,600-sample window, frame interval, `max_frames`);
- class-index orientation and score transform (`softmax[1]`, `softmax[0]`, `sigmoid(logit − boundary)`);
- aggregation (`mean` over frames) and coverage rules;
- thresholds (`0.5` in analyzers, `DEEPTRACE_DECISION_THRESHOLD` in `ml/detectors.py`). They are currently duplicated, so keep them in sync;
- the Community Forensics `raw_logit_boundary`, and the unused `calibration` / `target_probability_threshold` config fields.

Hard rules:

- Scores are uncalibrated. Keep `calibrated_probability=None` and `threshold_validated=False` unless a calibration or validation has actually been fitted on a documented dataset and versioned.
- No cross-detector fusion. `overall_synthetic_confidence` stays `None`. `CombinedVideoAnalyzer` is not to be re-wired without an explicit request.
- Do not change the production default (`DEEPTRACE_VIDEO_MODEL`, `DEEPTRACE_AUDIO_MODEL`, Dockerfile `ENV` commands) unless explicitly asked.
- Experimental adapters stay in `deeptrace/experimental/` and are never imported by `api.py`.
- Benchmarks report at the independent video/utterance level with frozen checkpoints, splits and thresholds (`docs/evaluation.md`, `experiments/`). Never tune thresholds on test data.
- Never commit checkpoints, datasets, `vendor/`, uploads, or results (all git-ignored).

## Tests

- `tests/test_analyzers.py` covers adapters with fake runner commands. Add a case for every new adapter (success, unavailable, error, timestamp preservation).
- `tests/test_api.py` and `tests/test_workflow.py` cover HTTP and workflow behavior.
- `tests/explainability/` contains a Grad-CAM sanity test that is skipped without model dependencies.
- CI also runs `python -m compileall -q deeptrace scripts tests`.
