# DeepTrace adaptation results — verified November 12, 2026

The adapted scene classifier substantially reduced false alarms on the same 57-file test, but the complete app still falls short of the 85% accuracy target under the frozen rule that counts incomplete files as incorrect. No production model/rule was changed during this review.

| Complete five-detector app, same 57 test files | Original | Adapted |
| --- | ---: | ---: |
| Correct / selected files | 41/57 | 46/57 |
| Accuracy, incomplete counted incorrect | 71.93% | 80.70% |
| Genuine recordings flagged | 7/27 | 1/27 |
| FPR, all genuine | 25.93% | 3.70% |
| FPR, decidable genuine | 36.84% (7/19) | 5.26% (1/19) |
| Manipulated recordings flagged | 29/30 | 28/30 |
| Recall, all manipulated | 96.67% | 93.33% |
| Incomplete files | 9 | 8 |
| Accuracy on decidable files only | 85.42% (41/48) | 93.88% (46/49) |
| Reports generated/stored/retrieved, workspaces retrieved | 57/57 | 57/57 |

The 93.88% figure excludes eight incomplete files and must not be presented as accuracy across all submitted files. Overall FPR meets the numerical <10% target on this small test; overall accuracy does not meet 85%. Neither establishes DPS operational acceptance.

## What improved and what remains

- All six scene-caused genuine FF++ false alarms disappeared. The remaining false alarm is genuine audio `LA_E_6154503`, flagged by both AASIST and LFCC-LCNN. On the nine genuine audio test files this is 1/9 = 11.11%; the overall 1/27 rate should not conceal that category result.
- Community Forensics independently improved from 14/16 (87.5%) to 16/16 on the generated-imagery category, detecting all 8 generated test videos with 0/8 genuine MSVD false alarms. Including the 10 genuine FF++ hard negatives, the scene check has 0/18 known-genuine video false alarms. Small sample, no broad 100%-accuracy claim.
- Eight genuine MSVD videos remain incomplete because the face check could not establish usable coverage: seven return no scored crop, and one scores only 1/7 sampled frames. Six of those seven unavailable clips have no dlib detections; the remaining one has a detected but unalignable face in 1/10 frames. The scene model completed and stayed below threshold. No face detection does not prove that no face exists, and the frozen evaluation correctly does not relabel these abstentions as true negatives.
- The two full-app false negatives are `FaceShifter/494_445.mp4` and `FaceShifter/445_494.mp4`, one correlated source pair. The unchanged face detector already missed them in both variants; the original scene detector happened to flag them. Its new, quieter scene rule exposes the pre-existing face-detection gap. Face model weights/scores did not regress.
- Independent face check: 18/20 correct, 8/10 manipulation recall, 0/10 genuine false alarms. AASIST: 20/21 correct, 12/12 spoof recall, 1/9 genuine false alarms. LFCC: 18/21 correct, 10/12 spoof recall, 1/9 genuine false alarms. CNNDetection flagged no generated-imagery example (8/16 overall, 0/8 generated recall). Artifact outputs do not establish audio-specific correctness on generated videos with unlabeled audio tracks.

## Protocol and provenance

The full manifest has 240 files, split into 132 training, 51 development and 57 test files. Source-group counts are 86 / 31 / 31 with no group or file-ID overlaps. All 12 previously observed smoke files and their related groups are training-only. The scene head actually used 68 training videos (44 genuine / 24 generated) and 26 development videos (18 genuine / 8 generated); audio and face-manipulated clips were not given invented scene labels. Exact hashes of all staged training/development/test content are disjoint. Unknown pretrained overlap, speakers shared with earlier experiments, unknown prompt relationships and non-DPS source mix remain limitations.

Only the 384-dimensional linear head was adapted. It contains 385 finite float32 values, 1,676 bytes total, SHA256 `58b0f4b156762314d3ef27ea4ea71c348299afe7a39fb2acd113f3f70b0d5b43`. Epoch 100 was selected from the predeclared 10/30/100 grid using development results; its frozen raw-logit boundary is `0.04392189905048009`. The base Community Forensics model stayed SHA256 `2f445aecc310caee9b55d3ae0aeebc404a32d72e5836e30523ce0a9a1720cd47`. All other detector scores, samples, coverage, thresholds, weights and revisions are identical between the two runs. Both report/workspace banners agree for every file.

The recorded runtime is Tesla T4, Python 3.13 environment, torch 2.11.0+cu130, torchvision 0.26.0+cu130, torchaudio 2.11.0+cu130. dlib 19.24.6 / CMake 3.31.6 / setuptools 80.9.0 / wheel 0.45.1 confirm the pinned installer repair was used. All five inference commands explicitly use CUDA. Saved availability/commands are not a historical GPU utilization trace. Baseline and candidate screening elapsed times are 1,179.817 and 1,161.953 seconds (about 19.7 and 19.4 minutes), excluding setup, transfer and training.

## Audit and limits

The archive is 993,852 bytes, SHA256 `6d5c1a39dc8926da0ed0935d2b113b62a449f81900a07a08a0f63ac087b3febf`. Read all 9 outer and 120 nested archive members. Recomputed every saved scene sample from its raw logit and frozen boundary, within-detector means, all report/workspace decisions, complete exported summaries/CSVs, confusion counts, FPR denominators, and head/protocol/input fingerprints. Original archives, detailed per-file records and derived verification outputs are retained outside Git. This document is the sanitized summary for repository review; datasets, uploaded media, credentials and checkpoint files are not part of the PR.

The nested ZIPs omit the shared input-receipt file because it lives outside their variant folders. The audit reconstructed it from the frozen test split and retained per-file fields and verified its exact original protocol hash. The top-level summary `rule_version` names report v1 while the protocol correctly names primary workspace v2; both banner rules and metrics replay correctly. These export-label issues do not change the numeric results.

This is a complete saved-evidence audit, not an independent inference/training rerun. The archive lacks source media, frozen feature arrays and per-development prediction ledgers, so training cannot be independently refitted or all development candidate metrics regenerated. Hash consistency and disjointness support the declared protocol but do not independently prove execution order or absence of external prior tuning. This revealed test must remain evaluation evidence, not become a threshold-tuning set.

The checked experiment implementation is in [`commfor_adaptation.py`](../backend/experiments/commfor_adaptation.py), [`kaggle_banner.py`](../backend/experiments/kaggle_banner.py) and [`tool_evaluation.py`](../backend/experiments/tool_evaluation.py). Notebook generation needs the separately retained frozen selection/model metadata; those local assets and the original result archives are not included in Git. The audit utility is retained with the local evidence, rather than advertised here as a complete public inference reproduction.

## Earlier independent archive references

- `deeptrace-audio-results.zip`: 68,315 bytes; SHA256 `713f82d12ee9d3abd17c4b4e726215aa55176ef947dcbbeb764c40a4beaaef6b`. Original AASIST first-window rule: TP93/TN100/FP0/FN7 on 200 test utterances; 96.5% accuracy, 0% observed FPR, 93% spoof recall. No fine-tuning. The separate development-selected rule produced 93.0% accuracy and was not promoted over the original audio rule.
- `deeptrace-face-results.zip`: 206,664 bytes; SHA256 `a6bf5331369793b36b9e96c0c723ec51b4b7b130719918cd3e061e474a9c810a`. Fixed face PoC rule: TP36/TN39/FP1/FN4 on 80 test videos; 93.75% accuracy, 2.5% FPR, 90% manipulation recall. The original any-frame 0.5 rule gave TP40/TN14/FP26/FN0. Threshold selection used 80 separate development videos, without weight fine-tuning. Source pairs are correlated; checkpoint training split is not fully verified.

The headline 93.9% completed-result accuracy is 46/49 with eight excluded incomplete files. It must remain accompanied by its exclusion count and the 46/57 all-file result. A complete report is not the same as a decisive model assessment: all 57 reports were produced even though eight assessments remained incomplete.

Next work should separately address face applicability/coverage and the FaceShifter weakness using new development data, then run a fresh frozen test. Retain the scene candidate as an opt-in research checkpoint until that full-app validation is complete.
