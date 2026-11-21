#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p vendor models/effort models/nes2net models/aasist models/efficientnetb4
clone_pinned() {
  local url="$1" target="$2" revision="$3"
  if [[ -e "$target" ]]; then
    if [[ "$(git -C "$target" rev-parse HEAD)" != "$revision" ]]; then
      printf 'Unexpected revision in %s; preserve it and choose a fresh checkout.\n' "$target" >&2
      exit 1
    fi
  else
    git clone "$url" "$target"
    git -C "$target" checkout --detach "$revision"
  fi
  git -C "$target" rev-parse HEAD > "$target/.deeptrace-revision"
}
if [[ "${1:-}" == "poc-artifacts" ]]; then
  clone_pinned https://github.com/PeterWang512/CNNDetection.git vendor/CNNDetection ea0b5622365e3a9cd31d1b54b6b5971131a839ab
  clone_pinned https://github.com/asvspoof-challenge/2021.git vendor/asvspoof2021 9b33f5eca887bd3bf629e3fb79428cd9bb7ac972
  clone_pinned https://github.com/genbing99/SoftNet-SpotME.git vendor/SoftNet-SpotME dd43d1e1d5ae471998ceb3be3177e2d9517c58fd
  printf '%s\n' 'Pinned optional PoC sources installed; run download_public_assets.sh poc-artifacts.'
  exit 0
fi
if [[ "${1:-}" != "core" ]]; then
  clone_pinned https://github.com/YZY-stack/Effort-AIGI-Detection.git vendor/Effort-AIGI-Detection 96f5dea2b534d400cfd7003f053c7e93c8e16461
  clone_pinned https://github.com/Liu-Tianchi/Nes2Net_ASVspoof_ITW.git vendor/Nes2Net_ASVspoof_ITW c9fe1177f44040f002cb40def928332d2e261f1e
fi
clone_pinned https://github.com/clovaai/aasist.git vendor/aasist a04c9863f63d44471dde8a6abcb3b082b07cd1d1
clone_pinned https://github.com/SCLBD/DeepfakeBench.git vendor/DeepfakeBench f188b1c105465e2e5377eb536a95022ae0e4522d
printf '%s\n' 'Pinned source installed. See docs/models.md for environments and checkpoints.'
