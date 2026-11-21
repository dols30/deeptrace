# Scene false-positive reduction experiment

The 12-file five-detector smoke run found two genuine FF++ false alarms caused solely by Community Forensics. Its genuine scores (~0.99) exceeded its two generated-video scores (~0.80–0.83), so increasing one threshold cannot separate these four examples. Four clips had no aligned face; coverage changes cannot convert those abstentions into correct negatives.

## Deliverable

`04_Kaggle_Scene_Adaptation_Heldout.ipynb`, built without network transfers:

```sh
PYTHONPATH=backend backend/.venv/bin/python -m experiments.build_commfor_adaptation artifacts/poc-tool-kaggle-workspace
```

The builder packages allowlisted working-tree app sources and records their hashes plus the base Git revision. It never includes `.env`, credentials, model weights, datasets, or uploaded media. Import the new notebook into a private hosted Kaggle notebook; add the same pinned inputs, Internet and GPU. Review the printed sizes and source terms, then enable both download/terms settings. Run development first, then the fixed holdout, and export `deeptrace-adaptation-results.zip`. Preserve a Kaggle version with outputs. The notebook refuses Mac execution.

## Fixed protocol

- Reuse the original 240-file manifest; group splits are approximately 60% training / 20% development / 20% test, stratified by source/method. All previously seen smoke groups are training-only. Exact counts/IDs are printed and frozen before scoring.
- Train only the Community Forensics linear head on frozen embeddings. MSVD and genuine FF++ are negatives; Sora/Veo3 are positives. Whole-file face/audio manipulation does not supply a scene label. Loss weights balance classes, then source groups, videos and frames.
- Preserve app RGB/resize/crop/normalization and 1-second/120-frame preparation. GPU extracts ViT features and runs the five-detector app. The small deterministic linear fit uses CPU. No new backbone is downloaded.
- Fixed AdamW learning rate 0.001, weight decay 0.01; epochs 10/30/100. Development chooses one checkpoint and raw-logit boundary maximizing generated recall with at most 5% observed FPR separately on genuine FF++ and MSVD. No test file or embedding is opened during selection. A small observed cap is not a population guarantee.
- Freeze the head/config/development evidence before opening holdout. Resume reuses frozen results; changed sources/settings/inputs/candidate are rejected. Do not refit after holdout results.
- Compare original and candidate on the same heldout files through the actual upload/report/workspace API with all five checks. All incomplete/error files stay in denominators, and flagged partial checks retain coverage warnings. Inspect per-category recall, scene FP contributions and report persistence as well as the overall banner.
- No automatic promotion; no production environment change; `calibrated_probability=null`. A failed candidate stays failed. Checkpoint training overlap, unknown prompt relationships, small correlated strata, non-DPS media and absent joint audio/face ground truth remain limitations.

## Download/storage budget

Same seven model/config assets: **462,832,401 bytes** at most, hash-verified Kaggle cache reused. Same selected generated media: **442,679,641 bytes** total, with train/dev/test amounts printed before transfer. Attached Kaggle audio/FF++ inputs are read in place. Public dependency/source transfers are additional. Frames are temporary and removed after extraction; compact feature caches and a tiny head are stored in Kaggle working storage. No media/model download is performed on the Mac by notebook creation.

## Verification and result status

Local tests cover group disjointness, seen-smoke exclusion from test, task labels, freeze/no-refit guards, coverage validation and banner v2 parity. Offline model checks compare exact preprocessing tensors, direct and frozen-feature/head logits, unchanged-head inference and mismatched-base rejection. Synthetic features exercise training/selection/resume mechanics; these are not accuracy evidence. Two existing local demo uploads passed isolated real-model/report/workspace integration, including persisted face counts. The completed Kaggle result archive has now been audited: the adapted five-detector app achieved 46/49 decisive-file accuracy (93.88%), excluding eight incomplete files from 57 selected; all-file accuracy was 46/57 (80.70%), and FPR was 1/27 (3.70%) across selected genuine files or 1/19 (5.26%) among decisive genuine files. The scene check improved from 14/16 to 16/16 on its generated-imagery category and removed six genuine FF++ false alarms. The selected head remains an opt-in candidate, not enabled in Docker. See [verified validation summary](../../docs/VALIDATION_RESULTS.md) for the remaining face coverage/miss and audio false-alarm issues.


## Kaggle dlib build recovery

The dlib dependency is still pinned to 19.24.6. Setup now installs it separately, reuses an importable matching version, and otherwise builds with CMake 3.31.6 / setuptools 80.9.0 / wheel 0.45.1, no build isolation, no dependency replacement, and one compiler worker. Full output is saved in `RUNTIME/dlib-build.log` with the last 100 lines printed on failure. The compiler failure reported by the user exposed no underlying CMake/C++ diagnostic, so its exact original cause is unconfirmed. This is installer hardening, not a detector/preprocessing change. The later successful result archive records dlib 19.24.6 and these pinned build-tool versions. The audit checked the saved runtime evidence; it did not recompile dlib locally.

For an already imported notebook, run `artifacts/poc-tool-kaggle-workspace/repair_dlib_kaggle.py` in a separate cell, then retry the failed setup cell without restarting. It installs the same dependency and leaves runtime source files/manifests untouched, preserving their fingerprints. The repair refuses Mac execution and fetches no datasets/model weights. Pinned build-tool wheel payload on Linux x86_64 is approximately 28–29 MB plus dlib source (~3.4 MB); pip may reuse already cached dependencies. Updated templates use a new runtime directory so existing extracted source is preserved.
