# PR scope and remaining validation work

This change documents the public-dataset validation and includes the coverage, experimental evaluation and optional local-login implementation reviewed with the project owner. The locally running app already includes the coverage and automatic-login changes. The adapted scene head remains disabled; merging this PR does not promote it.

## Documentation included

- Root README: public validation datasets and methods, earlier independent model studies, every evaluated classifier's later matched-task results, and both conditional/full-file app metrics. Highlight 93.9% only as 46/49 decisive results, with eight of 57 incomplete files explicitly excluded. Keep the original 46/57 = 80.7% all-file result and no overall PoC-completion claim.
- `docs/VALIDATION_RESULTS.md`: sanitized archive review, source/checkpoint hashes, split design, remaining errors and reproducibility limits. Original ZIPs, per-file evidence and checkpoints stay outside Git.
- `docs/API.md` / `docs/MODEL_REGISTRY.md`: additive coverage metadata, workspace banner behavior, local automatic-session contract, optional research-head provenance and verified result status.
- Experiment documentation: distinguish archived banner v1 from coverage-aware v2; record the completed Kaggle adaptation results and the pinned dependency-repair path.

## Implementation included

| Area | Existing working-tree change | Effect |
| --- | --- | --- |
| Face coverage | `scripts/inference/face_coverage.py`, EfficientNet runner, video adapter | Observe the upstream detector without changing its detections/crops; distinguish no detection, detected-but-unalignable, and scored frames. Validate counts; zero scored crops still abstain. |
| Persistence/API | Component coverage dictionary, detector metadata, workflow output/schema, TS mirrors | Preserve face/audio coverage in existing JSON metadata. Add optional workflow `coverage_limited`; no DB column or migration. |
| Investigator/report/PDF | Existing presentation components and shared helpers | Display measured coverage; keep limited unflagged screenings incomplete, while retaining any valid flags. Historical coverage notes remain readable. |
| Scene research mode | Shared CommFor preprocessing plus optional `--adaptation` loading | Preserve default inference pixels and release weights/rule. Strictly bind an external research head/config to the base SHA, preprocessing and frozen development rule. Do not enable the candidate by default. |
| Kaggle evaluation | Builders, hosted banner runner, grouped head-adaptation experiment, metrics/replay helpers | Fixed source-group splits, development-only selection, actual five-detector API/report/workspace testing, failed/incomplete retention, hashed resumability and bounded Kaggle-only transfers. |
| Dependency setup | Separate pinned dlib installer and torchaudio/scikit-image compatibility handling | Keep dlib 19.24.6; use compatible pinned build tools, one compiler worker, full diagnostics and existing-cache reuse. Preserve CUDA torch/torchvision. |
| Local sign-in | Opt-in setting, guarded local JWT endpoint, frontend session initialization/renewal, Compose | Backend credentials stay private; reuse employee identity and existing cases. Default off; reject sandbox/Cognito/nonlocal Host and unapproved Origin. Bind API/web ports to loopback. Explicit sign-out allows account switching. |
| Verification | Fake-runner backend tests, shared banner fixtures, frontend auth/coverage/PDF tests | Exercise fail-closed statuses, coverage persistence, banner parity, no-refit/split guards and local-session behavior. |

These changes do not introduce cross-detector score fusion, calibrated probabilities, new DB tables, altered default model weights or a published dataset/checkpoint.

## Decisions still needed before model promotion

1. The adapted head may be retained as an opt-in research candidate; enabling it in Docker is a separate change requiring explicit approval, an externally stored/hash-verified head/config, and command wiring. It is not included as a binary in this PR.
2. Eight genuine videos still have inadequate face coverage. Any future applicability rule must distinguish “no face” from “no detection” and keep coverage visible. Do not retroactively relabel the eight incomplete test files as correct negatives.
3. Two related FaceShifter clips remain missed by the face check. Study these limitations using separate development data, not by retuning on the now-revealed test.
4. The audio subset has one genuine false alarm among nine controls; CNNDetection missed all eight generated positives. These checks are not claimed to meet every target.
5. A future claim of complete PoC acceptance needs a frozen full-app evaluation with explicit eligibility/exclusion rules and the stakeholder's acceptance criteria, including an agreed runtime limit. The current conditional 93.9% figure alone is insufficient.

## Files to keep out of Git

- All `deeptrace-*-results.zip` attachments, original per-file evidence and media.
- `.env`, `backend/.env`, passwords, JWT secrets, generated tokens and database contents.
- `backend/models/`, external candidate heads/config assets, `backend/vendor/`, virtual environments and generated notebook/source bundles under `artifacts/`.
- Unrelated `.agents/` / `.opencode/` working-tree content unless reviewed separately.

The builders require the separately retained frozen metadata asset directory. The PR must not imply that those ignored assets, original evidence or notebooks are included automatically. If a self-contained notebook distribution is desired, review its small metadata/source bundle separately before publication.

## Verification already completed for the implementation

Last code checks: **180 backend tests passed, 4 skipped; 100 frontend tests passed; frontend typecheck and production build passed; backend compileall passed**. Local browser verification cleared the saved session and confirmed automatic employee sign-in. Existing cases remained accessible. The adaptation archive audit read all 129 outer/nested files and reproduced the saved decisions and metrics; it was not a new inference/training run.

No dataset download, model training or model promotion is part of preparing this PR. The evidence archives and local runtime settings remain outside Git; the project owner will review and merge the PR.
