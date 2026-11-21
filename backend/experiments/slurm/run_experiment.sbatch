#!/bin/bash
#SBATCH --job-name=deeptrace_eval
#SBATCH --partition=main
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --time=04:00:00
#SBATCH --output=deeptrace_eval.%j.out
#SBATCH --error=deeptrace_eval.%j.err

set -euo pipefail

if [[ $# -ne 3 ]]; then
  printf 'Usage: sbatch %s audio|video DATASET.csv OUTPUT_DIR\n' "$0" >&2
  exit 2
fi

repo_root="${SLURM_SUBMIT_DIR:?Submit this job from the DeepTrace repository root}"
cd "$repo_root"

module load miniconda/miniconda3 2>/dev/null || true

case "$1" in
  audio)
    model_env="${MODEL_ENV:-$HOME/envs/deeptrace-aasist}"
    export AASIST_PYTHON="${AASIST_PYTHON:-$model_env/bin/python}"
    export AASIST_WEIGHTS="${AASIST_WEIGHTS:-$HOME/deeptrace-models/aasist/AASIST.pth}"
    ;;
  video)
    model_env="${MODEL_ENV:-$HOME/envs/deeptrace-efficientnet}"
    export EFFICIENTNET_PYTHON="${EFFICIENTNET_PYTHON:-$model_env/bin/python}"
    export EFFICIENTNET_WEIGHTS="${EFFICIENTNET_WEIGHTS:-$HOME/deeptrace-models/efficientnetb4/effnb4_best.pth}"
    export LANDMARKS_WEIGHTS="${LANDMARKS_WEIGHTS:-$HOME/deeptrace-models/efficientnetb4/shape_predictor_81_face_landmarks.dat}"
    ;;
  *)
    printf 'Modality must be audio or video, got: %s\n' "$1" >&2
    exit 2
    ;;
esac

if [[ ! -x "$model_env/bin/python" ]]; then
  printf 'Missing model environment: %s\n' "$model_env" >&2
  exit 1
fi

if ! command -v conda >/dev/null 2>&1; then
  printf 'Conda was not found after loading miniconda/miniconda3\n' >&2
  exit 1
fi
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate "$model_env"

export HF_HOME="${HF_HOME:-$HOME/caches/hf}"
export HF_HUB_DISABLE_XET="${HF_HUB_DISABLE_XET:-1}"
export DEVICE="${DEVICE:-cuda}"

printf 'host=%s\n' "$(hostname -f 2>/dev/null || hostname)"
printf 'repo=%s\n' "$repo_root"
printf 'conda_prefix=%s\n' "$CONDA_PREFIX"
printf 'python=%s\n' "$(command -v python)"
python -V
nvidia-smi
python -c 'import torch; assert torch.cuda.is_available(), "CUDA is unavailable on this compute node"; print("gpu=" + torch.cuda.get_device_name(0))'
experiments/run_cluster_experiment.sh "$1" "$2" "$3"
