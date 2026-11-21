# Kaggle validation of the overall banners

This experiment exercises the actual upload → five subprocess adapters → report → saved report → persisted investigator workspace path. It evaluates both existing frontend banners, with the investigator workspace banner as primary. It does not change deployed models, thresholds, API schemas, database schemas or UI behavior. It does not fuse scores or train a rule.

`kaggle_banner.py` is the hosted runner. `tool_evaluation.py` mirrors the report overview and workspace officer summary. Shared fixtures run through the actual frontend functions/React component and Python mirrors. Archived workspace v1 could remain clear when the report overview warned about limited face coverage. The current workspace v2 preserves that coverage warning as incomplete; v1 remains available for historical replay. Disagreements are exported. Both banners agree for all 57 files in the audited adaptation test.

## Notebook and execution

The self-contained notebook is generated locally at:

`artifacts/poc-tool-kaggle-workspace/03_Kaggle_Five_Model_Banner_Validate.ipynb`

1. Import into a **new private Kaggle Notebook**. Enable Internet and an available GPU.
2. Attach `anishsarkar22/asvpoof-2019-dataset-la` **version 1**, and `abbasaliyev/ffpp-core-c23-videos` **version 2**, using Add Input. These full read-only inputs total approximately 18.61 GB on Kaggle, not on the Mac. Dataset protocols/index hashes must match the pinned versions.
3. Start with `RUN_SIZE='smoke'` (12 files). Read the displayed plan and linked source terms, then set the two notebook flags to enable cloud transfers and acknowledge compliant source use. All inference commands use CUDA; no CPU fallback is made. dlib/FFmpeg preprocessing still uses CPU.
4. Inspect smoke statuses, reports and workspaces. For the full benchmark, change `RUN_SIZE='full'` and rerun the configuration/setup/scoring/export cells, retaining the same audio policy. Cached model assets are hash-verified and reused. Changing the audio policy requires a fresh run/kernel. Full runs retain every selected file, including incomplete/error results.
5. Save a successful Kaggle version with outputs and retain `deeptrace-banner-full-results.zip`. Export contains protocol, source/model/input hashes, reports, workspaces, summary and per-file CSV; it excludes raw media, checkpoints, databases and credentials.

The notebook packages allowlisted app source from the working tree plus explicitly hashed experiment modules. Its manifest identifies the base Git revision and working-tree overlays; that revision alone is not claimed to identify all bundled bytes. No private GitHub clone or user credentials are needed. `build_kaggle_banner.py` accepts the directory containing the already frozen small metadata assets; it does not discover/download datasets. Rebuild from the repository root:

```sh
backend/.venv/bin/python backend/experiments/build_kaggle_banner.py artifacts/poc-tool-kaggle-workspace
backend/.venv/bin/python artifacts/poc-tool-kaggle-workspace/verify_notebook.py
```

## Five-detector profile

- DeepfakeBench EfficientNet-B4: pinned FF++ checkpoint/source/landmarks and development-selected `ffpp_c23_kaggle_v1` any-frame threshold **0.9967585206031799**; 1-second sampling, 120-frame cap.
- Community Forensics: pinned frontier checkpoint/config and existing mean-frame 0.5 rule.
- AASIST: original checkpoint, **full-recording window mode** by default; existing mean/window/0.5 handling.
- CNNDetection: pinned blur/JPEG checkpoint/source; uncropped RGB/ImageNet preprocessing and mean-frame 0.5 rule.
- LFCC-LCNN: official DF checkpoint/source and existing full-recording segmentation/any-window 0.5 handling.

Model metadata and constraints are in [MODEL_REGISTRY.md](../../docs/MODEL_REGISTRY.md). The inspected Docker deployment has only the three core classifiers enabled and first-window AASIST; this five-detector experiment explicitly evaluates the extended profile, not a claim that Docker is configured identically. Descriptive review measurements and SoftNet do not drive either banner and remain unconfigured.

Kaggle's CUDA torch/torchvision are preserved. LFCC's upstream module imports torchaudio. If a compatible one is missing, setup installs only the recorded compatible torchaudio wheel with `--no-deps`, using the matching CUDA index. TorchAudio 2.11's stable ABI supports torch 2.11 onward; earlier releases use matching versions, per [official installation documentation](https://docs.pytorch.org/audio/stable/installation.html). All installed versions are frozen in the evidence protocol. There is no model-training or fitted-calibration step.

## Selection and transfer sizes

Seed **20261112**, frozen before inference. Full test: **240 files**, each category balanced 40 genuine / 40 manipulated:

| Category | Input | Selection and byte plan |
| --- | --- | --- |
| Audio spoofing | ASVspoof2019 LA eval, Kaggle v1 | 80 fresh utterances, grouped by speaker/attack for selection; all 400 previously scored dev/test IDs excluded. WAV decoded losslessly from FLAC inside Kaggle. Exact selected byte counts printed before staging. |
| Face manipulation | FF++ c23, Kaggle v2 | 80 videos, 20 previously unused official test source pairs; 40 genuine plus 8 each Deepfakes/Face2Face/FaceSwap/NeuralTextures/FaceShifter. **142,900,304 bytes read in place**, no media network download. All previous dev/test source-sequence IDs excluded. |
| Generated imagery | `OmerXYZ/comgenvid` pinned `17f9ab6c548d9a30f5b22c09e17daee74536b653` | 40 genuine MSVD + 20 Sora + 20 Veo3; **442,679,641 bytes** downloaded inside Kaggle only. Eligibility 2–20 seconds and minimum dimension 240; one sample per source-video/creator group where identifiable. No outcome-based selection. |

The 12-file smoke selection uses four files per category, including both Sora and Veo3, and downloads **25,968,307 bytes** of generated video. All seven model/config assets total **462,832,401 bytes**; repeated valid files are reused. Thus initial smoke payload is **488.80 MB**, and full payload is **905.51 MB**, plus public source/dependencies. Source media and working copies occupy additional Kaggle disk space; neither full attached dataset is extracted/copied. No dataset/model downloads occur on the Mac. The notebook first cell rejects Mac execution.

Public generated-video source: [ComGenVid publisher card](https://huggingface.co/datasets/OmerXYZ/comgenvid/blob/17f9ab6c548d9a30f5b22c09e17daee74536b653/README.md). Card and Sora creator credits are bundled. Publisher labels/rights apply; public access does not grant unrestricted republication. FF++ research terms remain applicable to its Kaggle mirror.

## Results and limits

`summary.json` records:

- `overall` and `by_category`: investigator workspace decision metrics, with incomplete/error/demo counted incorrect in the headline denominator; both all-genuine and decidable-genuine FPR; recall and decision coverage.
- `report_overview` and `banner_disagreements`: separate upload report results and mismatches with the persisted workspace.
- `per_detector_on_appropriate_category`: independent detector metrics only on the corresponding labelled task. A generated video's whole-file label is not treated as an audio-spoof or face-manipulation label.
- `flag_contributions`: each detector's flag/false-alarm counts, including sole-flagger counts. A comparison removes the two artifact checks from the same existing outputs, retaining the same AASIST policy; it is a diagnostic replay, not a trained ensemble or independent historical Docker run.
- report/workspace retrieval, statuses, missing checks, limited face coverage, timing, immutable source/model/input fingerprints, and per-file evidence.

No overall AUROC/EER is meaningful for a categorical banner with no fused continuous score. The 85% accuracy and strictly <10% FPR comparison is descriptive subset reporting; it is suppressed for smoke/partial runs. `poc_acceptance_established` remains false. Results depend on the category/class mixture, correlated sources and completeness. Fresh utterances can share earlier speakers; checkpoint-training overlap and generated prompt independence remain unknown. This is not operational DPS validation or a dedicated benchmark of simultaneous manipulated speech and faces.

Resume is limited to the exact protocol/input fingerprints and preserved evidence. Completed errors are not silently rescored/replaced. A new Kaggle runtime does not automatically retrieve previous temporary files; preserve versions and evidence explicitly.

## Local verification

Run backend tests from `backend/` and frontend tests/typecheck from `frontend/`, as documented in the root agent guide. The offline source-package verifier also checks embedded hashes, byte budgets, exclusions, dataset selection and Mac safety. A separate ignored CPU integration check uses real pretrained audio and video inference through an isolated TestClient with temporary SQLite stores; it does not modify the running app or establish Kaggle/CUDA results.


## Python 3.13 setup repair

The original notebook pinned scikit-image 0.24.0, which has no CPython3.13 Linux wheel. The corrected cloud setup selects 0.25.2 specifically on Python3.13, retains 0.24.0 on older Python, and requires a binary scikit-image distribution. pip logging stays visible. The exact `_umeyama` and `SimilarityTransform` definitions used by upstream face alignment are AST-equivalent between the two official release sources. Detector code, checkpoints, sampling, orientation, aggregation and rules are unchanged; the installed package version is captured in the protocol.

The existing-session patch is `artifacts/poc-tool-kaggle-workspace/repair_python313.py`. Paste it into a new Kaggle cell after the failure and run it once, then rerun only the failed setup cell. It verifies the released helper hash, preserves backups, updates the source manifest and reloads the helper. It refuses unknown edits or a run that already contains frozen protocol/prediction evidence. The original bootstrap cell should not be rerun after this repair: it contains the old embedded source and intentionally rejects edited files. No GPU restart or dataset transfer is required by this patch. The revised notebook uses a versioned runtime directory for future imports.

Primary references: [0.24.0 release files](https://pypi.org/project/scikit-image/0.24.0/#files), [0.25.2 release files](https://pypi.org/project/scikit-image/0.25.2/#files), and official source [`v0.24.0`](https://github.com/scikit-image/scikit-image/blob/v0.24.0/skimage/transform/_geometric.py) / [`v0.25.2`](https://github.com/scikit-image/scikit-image/blob/v0.25.2/skimage/transform/_geometric.py).
