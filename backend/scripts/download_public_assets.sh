#!/usr/bin/env bash
set -euo pipefail
model_assets_root="$(cd "$(dirname "$0")/.." && pwd)"

usage() {
  cat <<'EOF'
Usage: scripts/download_public_assets.sh models [DESTINATION]
       scripts/download_public_assets.sh community-forensics [DESTINATION]
       scripts/download_public_assets.sh poc-artifacts [DESTINATION]
       scripts/download_public_assets.sh wavefake [DESTINATION]
       scripts/download_public_assets.sh asvspoof2021-df [DESTINATION]
       scripts/download_public_assets.sh asvspoof2021-df-part00 [DESTINATION]

Downloads public, ungated experiment assets with curl resume support and writes
SHA-256 checksums beside them. Large datasets are never downloaded implicitly.

Defaults:
  models destination:   backend/models (relative to this script, not the caller)
  wavefake destination: /cluster/datasets/deeptrace/archives/wavefake-1.2.0
  ASVspoof destination: $HOME/deeptrace-data/asvspoof2021-df/archives
EOF
}

file_sha256() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

download() {
  local url="$1" output="$2" expected_sha256="${3:-}"
  mkdir -p "$(dirname "$output")"
  if [[ -f "$output" && -n "$expected_sha256" ]] && [[ "$(file_sha256 "$output")" == "$expected_sha256" ]]; then
    printf 'Verified cached asset: %s\n' "$output"
    return
  fi
  if [[ -f "$output" ]]; then
    printf 'Resuming or validating %s\n' "$output"
  else
    printf 'Downloading %s\n' "$output"
  fi
  curl --fail --location --retry 5 --retry-delay 5 --continue-at - \
    --output "$output" "$url"
  local actual_sha256
  actual_sha256="$(file_sha256 "$output")"
  if [[ -n "$expected_sha256" && "$actual_sha256" != "$expected_sha256" ]]; then
    printf 'SHA-256 mismatch for %s: expected %s, got %s\n' \
      "$output" "$expected_sha256" "$actual_sha256" >&2
    exit 1
  fi
  printf '%s  %s\n' "$actual_sha256" "$output" > "${output}.sha256"
}

command="${1:-}"
case "$command" in
  poc-artifacts)
    destination="${2:-${model_assets_root}/models}"
    download 'https://www.dropbox.com/s/2g2jagq2jn1fd0i/blur_jpg_prob0.5.pth?dl=1' \
      "${destination}/cnn_artifacts/blur_jpg_prob0.5.pth" \
      '3533f3e58a3b82215f21197f2faf4e99b911ec42a4a6e2d7823e04d5f3fd245a'
    download 'https://www.dropbox.com/sh/gf3zp00qvdp3row/AABg4OUDKFvFonI-HmIzT5qIa/temp/asvspoof2021/df_trained_network.pt?dl=1' \
      "${destination}/lfcc_lcnn/df_trained_network.pt" \
      '7cee483813b118039cc3d63d24f744cf99303f5cfaffa5886eabecda91586b61'
    download 'https://raw.githubusercontent.com/genbing99/SoftNet-SpotME/dd43d1e1d5ae471998ceb3be3177e2d9517c58fd/SOFTNet_Weights/CASME_sq/micro-expression/s1.hdf5' \
      "${destination}/softnet/CASME_micro_s1.hdf5" \
      '5094d6ab73e11037a04a928b04551939b840416a12fbf5a8a07fe64386117ecd'
    ;;
  models)
    destination="${2:-${model_assets_root}/models}"
    aasist_revision=16774d458d86d2a021ae31646c1bf66a5331b53e
    download \
      "https://huggingface.co/SpeechAntiSpoofingBenchmarks/AASIST/resolve/${aasist_revision}/AASIST.pth" \
      "${destination}/aasist/AASIST.pth" \
      "51d2d9cf0738172f61e2a384ec50a54a55363240f67c971ed55a92435bc1a1c0"
    download \
      "https://github.com/SCLBD/DeepfakeBench/releases/download/v1.0.1/effnb4_best.pth" \
      "${destination}/efficientnetb4/effnb4_best.pth" \
      "74cbd82d7be1bf5e6adec717824274a95b4509b02e1e78401608d32b3cbeaf0f"
    download \
      "https://github.com/SCLBD/DeepfakeBench/releases/download/v1.0.0/shape_predictor_81_face_landmarks.dat" \
      "${destination}/efficientnetb4/shape_predictor_81_face_landmarks.dat" \
      "8cae4375589dd915d9a0a881101bed1bbb4e9887e35e63b024388f1ca25ff869"
    ;;
  community-forensics)
    destination="${2:-${model_assets_root}/models}"
    release='https://huggingface.co/Thermostatic/community-forensics-frontier-detector-2026-08/resolve/16db135220b318d811b207db576d90368980b595'
    download "$release/model.safetensors" "${destination}/commfor/frontier.safetensors" \
      '2f445aecc310caee9b55d3ae0aeebc404a32d72e5836e30523ce0a9a1720cd47'
    download "$release/config.json" "${destination}/commfor/config.json" \
      '17cc7d383a872107f43b8603e81081530ac86ef9fb4564e7f2c2ba34342989c1'
    ;;
  wavefake)
    destination="${2:-/cluster/datasets/deeptrace/archives/wavefake-1.2.0}"
    mkdir -p "$destination"
    download \
      "https://zenodo.org/records/5642694/files/generated_audio.zip?download=1" \
      "${destination}/generated_audio.zip"
    expected_md5=76b3e62d69f866e57ad6b1debaff434b
    actual_md5="$(md5sum "${destination}/generated_audio.zip" | awk '{print $1}')"
    if [[ "$actual_md5" != "$expected_md5" ]]; then
      printf 'WaveFake MD5 mismatch: expected %s, got %s\n' "$expected_md5" "$actual_md5" >&2
      exit 1
    fi
    printf '%s  %s\n' "$actual_md5" generated_audio.zip > "${destination}/generated_audio.zip.md5"
    ;;
  asvspoof2021-df)
    destination="${2:-$HOME/deeptrace-data/asvspoof2021-df/archives}"
    mkdir -p "$destination"
    names=(
      ASVspoof2021_DF_eval_part00.tar.gz
      ASVspoof2021_DF_eval_part01.tar.gz
      ASVspoof2021_DF_eval_part02.tar.gz
      ASVspoof2021_DF_eval_part03.tar.gz
    )
    md5s=(
      4f2cbae07cf3ede2a1dde3b8d2ee55ea
      1578c89ab433c2b60b1dce93bdf8fbec
      5497a35f0126e94a1d7a7d26db57b4f7
      42b7512ba2943e98a32a53c9608cf83c
    )
    for index in "${!names[@]}"; do
      name="${names[$index]}"
      download "https://zenodo.org/records/4835108/files/${name}?download=1" \
        "${destination}/${name}"
      actual_md5="$(md5sum "${destination}/${name}" | awk '{print $1}')"
      if [[ "$actual_md5" != "${md5s[$index]}" ]]; then
        printf 'ASVspoof MD5 mismatch for %s: expected %s, got %s\n' \
          "$name" "${md5s[$index]}" "$actual_md5" >&2
        exit 1
      fi
      printf '%s  %s\n' "$actual_md5" "$name" > "${destination}/${name}.md5"
    done
    download "https://www.asvspoof.org/asvspoof2021/DF-keys-full.tar.gz" \
      "${destination}/DF-keys-full.tar.gz"
    actual_md5="$(md5sum "${destination}/DF-keys-full.tar.gz" | awk '{print $1}')"
    if [[ "$actual_md5" != dabbc5628de4fcef53036c99ac7ab93a ]]; then
      printf 'ASVspoof key archive MD5 mismatch: got %s\n' "$actual_md5" >&2
      exit 1
    fi
    printf '%s  %s\n' "$actual_md5" DF-keys-full.tar.gz > "${destination}/DF-keys-full.tar.gz.md5"
    ;;
  asvspoof2021-df-part00)
    destination="${2:-$HOME/deeptrace-data/asvspoof2021-df-part00/archives}"
    mkdir -p "$destination"
    name=ASVspoof2021_DF_eval_part00.tar.gz
    download "https://zenodo.org/records/4835108/files/${name}?download=1" \
      "${destination}/${name}"
    actual_md5="$(md5sum "${destination}/${name}" | awk '{print $1}')"
    if [[ "$actual_md5" != 4f2cbae07cf3ede2a1dde3b8d2ee55ea ]]; then
      printf 'ASVspoof MD5 mismatch for %s: got %s\n' "$name" "$actual_md5" >&2
      exit 1
    fi
    printf '%s  %s\n' "$actual_md5" "$name" > "${destination}/${name}.md5"
    download "https://www.asvspoof.org/asvspoof2021/DF-keys-full.tar.gz" \
      "${destination}/DF-keys-full.tar.gz"
    actual_md5="$(md5sum "${destination}/DF-keys-full.tar.gz" | awk '{print $1}')"
    if [[ "$actual_md5" != dabbc5628de4fcef53036c99ac7ab93a ]]; then
      printf 'ASVspoof key archive MD5 mismatch: got %s\n' "$actual_md5" >&2
      exit 1
    fi
    printf '%s  %s\n' "$actual_md5" DF-keys-full.tar.gz > "${destination}/DF-keys-full.tar.gz.md5"
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
