# Evaluation datasets

Use only data whose terms have been reviewed for this project. Keep all media
outside Git and record the downloaded release, source URL, retrieval date,
license or agreement, archive checksum, and the exact file-level split.

## Recommended starting set

| Modality | Dataset | Purpose | Access |
| --- | --- | --- | --- |
| Audio | ASVspoof 2021 DF | Primary out-of-domain audio evaluation | Public Zenodo release; ODC Attribution |
| Audio | ASVspoof 2021 LA | Channel-robustness evaluation | Public Zenodo release; ODC Attribution |
| Audio | WaveFake 1.2.0 | Cross-generator and cross-language evaluation | Public Zenodo release; CC BY-SA 4.0; generated audio only |
| Video | FaceForensics++ | In-domain check for the proposed FF++ checkpoint | Request access and accept the provider's terms |
| Video | FakeAVCeleb | Joint fake-video and cloned-audio evaluation | Request access; research/education terms |
| Video | DFDC | Cross-dataset evaluation on rights-cleared actors | Kaggle access after accepting competition data terms |
| Video | DeeperForensics-1.0 | Perturbation and domain-shift evaluation | Request access; non-commercial research terms |

Official sources:

- ASVspoof 2021 releases: <https://www.asvspoof.org/index2021.html>
- ASVspoof 2021 DF: <https://zenodo.org/record/4835108>
- ASVspoof 2021 LA: <https://zenodo.org/record/4837263>
- WaveFake 1.2.0: <https://zenodo.org/records/5642694>
- FaceForensics++: <https://github.com/ondyari/FaceForensics>
- FakeAVCeleb: <https://github.com/DASH-Lab/FakeAVCeleb>
- DFDC: <https://www.kaggle.com/c/deepfake-detection-challenge/data>
- DeeperForensics-1.0: <https://github.com/EndlessSora/DeeperForensics-1.0>

## Phase 1 order

1. Run AASIST on ASVspoof 2021 DF without using it for threshold selection.
2. Run AASIST on WaveFake as a second, independent generator family check.
3. Run EfficientNet-B4 on the official FaceForensics++ split matching the
   checkpoint's training provenance.
4. Run the same frozen video configuration on FakeAVCeleb or DFDC.
5. Use FakeAVCeleb to evaluate audio and video component outputs separately;
   do not treat two predictions from the same file as independent samples.

Start with a stratified subset for pipeline validation, then run the frozen
experiment on the full selected split. A small subset is not sufficient for a
final accuracy claim.

## Split rules

- Never place material derived from the same source video, utterance, or person
  in both development and evaluation sets.
- Do not tune a threshold on the final evaluation split.
- Report metrics per independent video or utterance, not per extracted frame.
- Preserve the provider's official split when one exists.
- Record unavailable media and face-detection failures as coverage failures.
- Evaluate authentic and synthetic media after matched transcoding so codecs do
  not become a shortcut label.

## Storage layout

```text
/cluster/datasets/deeptrace/
├── archives/                 # original downloaded archives, read-only
├── manifests/                # provenance and checksums
├── audio/
│   ├── asvspoof2021-df/
│   └── wavefake/
└── video/
    ├── faceforensics++/
    ├── fakeavceleb/
    └── dfdc/
```

Convert each selected split into the `id,path,label` CSV accepted by
`run_cluster_experiment.sh`, where `1` means synthetic/spoof and `0` means
authentic/bona fide.

## Fine-tuning boundary

Do not fine-tune on the Phase 1 evaluation files. If Phase 1 supports
fine-tuning or model replacement, create a separate licensed training set and
retain at least one untouched cross-dataset evaluation set for Phase 2.
