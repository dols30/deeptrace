#!/bin/bash
#SBATCH --job-name=asvspoof_prep
#SBATCH --partition=main
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --time=24:00:00
#SBATCH --output=asvspoof_prep.%j.out
#SBATCH --error=asvspoof_prep.%j.err

set -euo pipefail

repo_root="${SLURM_SUBMIT_DIR:?Submit this job from the DeepTrace repository root}"
cd "$repo_root"

module load miniconda/miniconda3 2>/dev/null || true
conda_env="${CONDA_ENV:-$HOME/envs/deeptrace}"
if [[ ! -x "$conda_env/bin/python" ]]; then
  printf 'Missing Conda environment: %s\n' "$conda_env" >&2
  exit 1
fi

data_root="${DATA_ROOT:-$HOME/deeptrace-data/asvspoof2021-df}"
mkdir -p "$data_root"

printf 'host=%s\n' "$(hostname -f 2>/dev/null || hostname)"
printf 'data_root=%s\n' "$data_root"
df -h "$data_root"

bash scripts/download_public_assets.sh asvspoof2021-df "$data_root/archives"
"$conda_env/bin/python" experiments/prepare_asvspoof2021_df.py \
  "$data_root/archives" "$data_root/eval" "$data_root/eval.csv"

printf 'manifest=%s\n' "$data_root/eval.csv"
wc -l "$data_root/eval.csv"
du -sh "$data_root"
