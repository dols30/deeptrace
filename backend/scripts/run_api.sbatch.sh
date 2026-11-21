#!/bin/bash
#SBATCH --job-name=deeptrace_api
#SBATCH --partition=main
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --time=04:00:00
#SBATCH --output=deeptrace_api.%j.out
#SBATCH --error=deeptrace_api.%j.err

set -euo pipefail

repo_root="${SLURM_SUBMIT_DIR:?Submit this job from the DeepTrace repository root}"
cd "$repo_root"

conda_env="${CONDA_ENV:-$HOME/envs/deeptrace}"
port="${PORT:-8080}"

module load miniconda/miniconda3 2>/dev/null || true

if [[ ! -x "$conda_env/bin/python" ]]; then
  printf 'Missing API environment: %s\n' "$conda_env" >&2
  printf 'Create it on the login node with:\n' >&2
  printf '  module load miniconda/miniconda3\n' >&2
  printf '  conda create -p %s python=3.12 -y\n' "$conda_env" >&2
  printf '  %s/bin/python -m pip install -r requirements.txt\n' "$conda_env" >&2
  exit 1
fi

if ! command -v conda >/dev/null 2>&1; then
  printf 'Conda was not found after loading miniconda/miniconda3\n' >&2
  exit 1
fi
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate "$conda_env"

export DEEPTRACE_UPLOAD_DIR="${DEEPTRACE_UPLOAD_DIR:-/tmp/deeptrace-uploads-$USER}"
mkdir -p "$DEEPTRACE_UPLOAD_DIR"

host="$(hostname -f 2>/dev/null || hostname)"
printf 'DeepTrace API: http://%s:%s/docs\n' "$host" "$port"
printf 'repo=%s\n' "$repo_root"
printf 'conda_prefix=%s\n' "$CONDA_PREFIX"
printf 'python=%s\n' "$(command -v python)"
python -V

exec python -m uvicorn deeptrace.main:app --host 0.0.0.0 --port "$port"
