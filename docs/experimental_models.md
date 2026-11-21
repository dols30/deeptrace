# Experimental detector setup

Experimental models are subprocess-only and are not imported by the production API. Large repositories, environments, datasets, predictions, and checkpoints are gitignored.

## FakeSTormer

- Official source: `https://github.com/10Ring/FakeSTormer`
- Audited revision: `c5b5f75100b878212a192c00013275f275f86182`
- Paper: *Vulnerability-Aware Spatio-Temporal Learning for Generalizable Deepfake Video Detection*, ICCV 2025.
- License: University of Luxembourg SnT academic license. It permits academic research/development/testing/validation only; other uses require a separate agreement.
- Official weights: Dropbox folder linked from the official README. The release does not publish stable filenames or checksums in the README, so record the selected file and SHA-256 locally after download.
- Expected local layout: `backend/experimental-assets/FakeSTormer/` and `backend/experimental-assets/checkpoints/fakestormer/<official-file>.pth`.
- Environment: separate CUDA environment/container. Official recommendation is Python ≥3.8, PyTorch 1.8.0, torchvision 0.9.0, CUDA 11.4, and mmcv 1.6.1 built from source. Do not install these over `.venv-models`.

Example setup:

```bash
git clone https://github.com/10Ring/FakeSTormer.git backend/experimental-assets/FakeSTormer
git -C backend/experimental-assets/FakeSTormer checkout c5b5f75100b878212a192c00013275f275f86182
# Build a dedicated CUDA 11 environment, then install requirements-fakestormer.txt
# and mmcv v1.6.1 with MMCV_WITH_OPS=1.
sha256sum backend/experimental-assets/checkpoints/fakestormer/*.pth
```

Adapter command template:

```bash
<isolated-python> experiments/fakestormer_official_runner.py \
  --repo experimental-assets/FakeSTormer \
  --config experimental-assets/FakeSTormer/configs/temporal/FakeSFormer_base_c23.yaml \
  --checkpoint experimental-assets/checkpoints/fakestormer/<official-file>.pth \
  --video {video_path}
```

## DeMamba

- Official source: `https://github.com/chenhaoxing/DeMamba`
- Paper: *DeMamba: AI-Generated Video Detection on Million-Scale GenVideo Benchmark*.
- Repository license: Apache-2.0.
- Status: **DeMamba: BLOCKED**.
- Reason: the audited official release does not provide a reproducible pretrained detector checkpoint plus complete single-video inference/preprocessing/score-orientation contract. No weights are downloaded and no alternative detector is silently substituted.

When official assets become available, place them below `backend/experimental-assets/checkpoints/demamba/`, record source URL/license/SHA-256, and implement the existing adapter contract in its own environment.

## Production safety

`deeptrace.api` imports only the production analyzers. Experimental adapters live under `deeptrace.experimental` and require explicit benchmark invocation. The normal application continues to use EfficientNet-B4, Community Forensics, and AASIST.
