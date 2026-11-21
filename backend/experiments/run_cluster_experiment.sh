#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  experiments/run_cluster_experiment.sh audio DATASET.csv OUTPUT_DIR
  experiments/run_cluster_experiment.sh video DATASET.csv OUTPUT_DIR

Required environment variables:
  Audio: AASIST_PYTHON, AASIST_WEIGHTS
  Video: EFFICIENTNET_PYTHON, EFFICIENTNET_WEIGHTS, LANDMARKS_WEIGHTS

Optional:
  DEVICE=cuda|cpu       Default: cuda
  AASIST_VARIANT=aasist|aasist-l
  FRAME_INTERVAL=1.0    Video sampling interval in seconds
  MAX_FRAMES=120

The dataset CSV must contain: id,path,label (label 1=synthetic, 0=real).
EOF
}

if [[ ${1:-} == "--help" || ${1:-} == "-h" ]]; then
  usage
  exit 0
fi
if [[ $# -ne 3 ]]; then
  usage >&2
  exit 2
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
modality="$1"
dataset="$2"
output_dir="$3"

if [[ ! -f "$dataset" ]]; then
  printf 'Dataset manifest not found: %s\n' "$dataset" >&2
  exit 2
fi

case "$modality" in
  audio)
    : "${AASIST_PYTHON:?Set AASIST_PYTHON to the AASIST environment python}"
    : "${AASIST_WEIGHTS:?Set AASIST_WEIGHTS to the reviewed AASIST checkpoint}"
    driver_python="$AASIST_PYTHON"
    ;;
  video)
    : "${EFFICIENTNET_PYTHON:?Set EFFICIENTNET_PYTHON to the EfficientNet environment python}"
    : "${EFFICIENTNET_WEIGHTS:?Set EFFICIENTNET_WEIGHTS to the reviewed detector checkpoint}"
    : "${LANDMARKS_WEIGHTS:?Set LANDMARKS_WEIGHTS to the 81-point dlib file}"
    driver_python="$EFFICIENTNET_PYTHON"
    ;;
  *)
    printf 'Modality must be audio or video, got: %s\n' "$modality" >&2
    exit 2
    ;;
esac

mkdir -p "$output_dir"
if [[ ! -x "$driver_python" ]]; then
  printf 'Environment Python is missing or not executable: %s\n' "$driver_python" >&2
  exit 2
fi

exec "$driver_python" "$repo_root/experiments/run_manifest.py" \
  "$modality" "$dataset" "$output_dir" \
  --repo-root "$repo_root" \
  --device "${DEVICE:-cuda}" \
  --aasist-python "${AASIST_PYTHON:-}" \
  --aasist-weights "${AASIST_WEIGHTS:-}" \
  --aasist-variant "${AASIST_VARIANT:-aasist}" \
  --efficientnet-python "${EFFICIENTNET_PYTHON:-}" \
  --efficientnet-weights "${EFFICIENTNET_WEIGHTS:-}" \
  --landmarks "${LANDMARKS_WEIGHTS:-}" \
  --frame-interval "${FRAME_INTERVAL:-1.0}" \
  --max-frames "${MAX_FRAMES:-120}"
