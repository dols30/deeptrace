# Cluster experiments

Keep these experiments in this repository so evaluation uses the exact pinned
adapters, preprocessing, and upstream revisions shipped with DeepTrace. Dataset
media, checkpoints, and results remain outside Git.

Review [the dataset catalog](DATASETS.md) before requesting or downloading
benchmark media.

`scripts/download_models.sh` downloads pinned **source code only**.
`scripts/download_public_assets.sh models` downloads the public AASIST and
DeepfakeBench EfficientNet-B4 checkpoints and records their SHA-256 checksums.
The AASIST mirror is pinned to a Hugging Face commit; compare it with the
official upstream checkpoint before treating it as an identical baseline.
Neither script downloads restricted datasets.

## Prepare the checkout

```bash
module load miniconda/miniconda3
cd ~/projects/deep_trace
bash scripts/download_models.sh
bash scripts/download_public_assets.sh models "$HOME/deeptrace-models"
cp experiments/dataset.example.csv /cluster/project/deeptrace/audio-eval.csv
```

WaveFake 1.2.0 is public but approximately 29 GB. Download it explicitly:

```bash
bash scripts/download_public_assets.sh wavefake \
  /cluster/datasets/deeptrace/archives/wavefake-1.2.0
```

The command resumes interrupted transfers and validates the publisher's MD5.
WaveFake contains generated audio only; obtain a license-compatible authentic
reference set before calculating balanced accuracy, FPR, or AUROC.

ASVspoof 2021 DF contains both bona-fide and spoof evaluation audio. Its four
archives total approximately 34.5 GB. Download, validate, extract, and build the
official-label manifest with:

```bash
df -h "$HOME"
bash scripts/download_public_assets.sh asvspoof2021-df \
  "$HOME/deeptrace-data/asvspoof2021-df/archives"
python experiments/prepare_asvspoof2021_df.py \
  "$HOME/deeptrace-data/asvspoof2021-df/archives" \
  "$HOME/deeptrace-data/asvspoof2021-df/eval" \
  "$HOME/deeptrace-data/asvspoof2021-df/eval.csv"
```

Keep enough space for both the 34.5 GB archives and extracted FLAC files during
preparation. Do not delete the validated archives until the extraction and
manifest counts have been checked.

For a preliminary result on limited storage, prepare only part 00 and select a
fixed 250-per-class subset:

```bash
sbatch --export=ALL,CONDA_ENV="$HOME/envs/deeptrace" \
  experiments/slurm/prepare_asvspoof2021_df_subset.sbatch
```

This uses roughly 8.6 GB for the archive plus its extracted audio and writes
`~/deeptrace-data/asvspoof2021-df-part00/eval-subset.csv` with a companion
metadata JSON recording the part, seed, protocol hash, and class counts.

Create separate Python environments for AASIST and EfficientNet-B4 as required
by their upstream dependencies. Do not install both ML stacks into the API
environment.

Load Miniconda at the start of every interactive cluster session and verify the
environment before running an experiment:

```bash
module load miniconda/miniconda3
conda activate ~/envs/deeptrace-aasist
which python
python -V
ls ~/envs/deeptrace-aasist/bin/python
~/envs/deeptrace-aasist/bin/python - <<'PY'
import torch
print("torch:", torch.__version__)
print("cuda available:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("gpu:", torch.cuda.get_device_name(0))
PY
```

The runner uses the full path to the environment Python. This also works in a
batch shell when `conda activate` is unavailable.

## Run interactively

Audio:

```bash
module load miniconda/miniconda3
export AASIST_PYTHON="$HOME/envs/deeptrace-aasist/bin/python"
export AASIST_WEIGHTS="$HOME/deeptrace-models/aasist/AASIST.pth"
export DEVICE=cuda
experiments/run_cluster_experiment.sh audio \
  /cluster/project/deeptrace/audio-eval.csv artifacts/audio-baseline
```

Video:

```bash
module load miniconda/miniconda3
export EFFICIENTNET_PYTHON="$HOME/envs/deeptrace-efficientnet/bin/python"
export EFFICIENTNET_WEIGHTS="$HOME/deeptrace-models/efficientnetb4/effnb4_best.pth"
export LANDMARKS_WEIGHTS="$HOME/deeptrace-models/efficientnetb4/shape_predictor_81_face_landmarks.dat"
export DEVICE=cuda
experiments/run_cluster_experiment.sh video \
  /cluster/project/deeptrace/video-eval.csv artifacts/video-baseline
```

The video runner preserves the product defaults: one frame per second, up to
120 frames. Override `FRAME_INTERVAL` or `MAX_FRAMES` only for an explicitly
named coverage experiment.

## Run with Slurm

The included Slurm file uses the `main` partition, one task, four CPUs, the
scheduler's default memory, and four hours. This cluster does not accept a GPU
GRES request; the job verifies CUDA access after it starts.

```bash
cd ~/projects/deep_trace
sbatch experiments/slurm/run_experiment.sbatch audio \
  /cluster/project/deeptrace/audio-eval.csv artifacts/audio-baseline
```

The job defaults to `~/envs/deeptrace-aasist` for audio and
`~/envs/deeptrace-efficientnet` for video. Override the default when needed:

```bash
sbatch --export=ALL,MODEL_ENV=$HOME/envs/my-audio-env \
  experiments/slurm/run_experiment.sbatch audio DATASET.csv OUTPUT_DIR
```

## Outputs

Each output directory contains:

- `run.json`: dataset, host, device, asset hashes, and sampling configuration.
- `records.jsonl`: one complete success or failure record per media file.
- `scores.csv`: successful `id,label,score` rows for metric calculation.
- `metrics.json`: accuracy, false-positive rate, true-positive rate, AUROC, and
  confusion matrix when both classes are present.

Failures remain in `records.jsonl` and are excluded from `scores.csv`. Always
report failure/coverage counts alongside accuracy metrics.

## Overall banner on Kaggle

See [KAGGLE_BANNER.md](KAGGLE_BANNER.md) for the self-contained five-detector notebook, fixed source-separated selections, download budgets, workspace/report banner parity checks and evidence exports. It starts with 12 smoke files and supports a frozen 240-file benchmark without changing production settings or fitting thresholds.

- [Scene adaptation / heldout comparison](SCENE_ADAPTATION.md): opt-in frozen-backbone head experiment targeting Community Forensics false alarms; no automatic promotion.
