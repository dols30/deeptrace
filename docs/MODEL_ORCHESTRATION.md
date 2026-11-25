# Model orchestration: parallel detectors, warm workers, GPU

How `/v1/analyze` runs its detectors, the two settings that make it faster, and the recommended AWS GPU host. Model semantics (preprocessing, class orientation, score transforms, aggregation, thresholds) are unchanged by everything here. See [MODEL_REGISTRY.md](MODEL_REGISTRY.md).

## Settings

| Setting | Default | Effect |
| --- | --- | --- |
| `DEEPTRACE_MAX_PARALLEL_RUNNERS` | `1` | Independent detector jobs run concurrently, up to this many at once (1 to 16). `1` runs them one after another, as before. |
| `DEEPTRACE_MODEL_WORKERS` | `false` | Each runner script is served by a long-lived worker process that keeps its model loaded, instead of a new process per upload. |
| `DEEPTRACE_DEVICE` / `DEEPTRACE_TORCH_INDEX` | `cpu` | Existing GPU switch (`cuda` / `cu126`). See [ALL_MODELS_SETUP.md](ALL_MODELS_SETUP.md#optional-nvidia-gpu-build). |

Both settings default to the previous behaviour. [`.env.prod.example`](../.env.prod.example) turns them on for the GPU host (`true`, `4`); [`.env.local.example`](../.env.local.example) leaves them off for the Mac.

## What runs in parallel

After `prepare_video` has extracted frames and audio, these jobs are independent and run concurrently (`api.py::_run_jobs`):

- the face detector (EfficientNet-B4 or Effort) and the whole-frame detector (Community Forensics), which read the frames directory;
- the audio detector (AASIST or Nes2Net), which reads the extracted WAV;
- the opt-in GAN-artifact and vocoder-artifact detectors;
- supplementary review measurements and micro-expression spotting.

Each job still produces its own `ComponentResult` or review checks. Results are collected in the original report order, and nothing is combined across detectors. Media probing and frame extraction stay sequential because every job depends on them.

On a CPU-only host, concurrency mostly shares the same cores. Keep the value low and cap per-runner threads (`OMP_NUM_THREADS` and related settings, as the `all-models` image target in `backend/Dockerfile` does). The real gains come from the GPU and from warm workers.

## Warm workers

Without workers, every detector call starts Python, imports torch, builds the model, loads and hashes the checkpoint, scores the input and exits. With `DEEPTRACE_MODEL_WORKERS=true`:

```text
adapter ──run_command()──▶ analyzers/runner.py ──Unix socket──▶ scripts/inference/worker.py (model venv)
                                   │                                    │ calls the same runner main(argv)
                                   └─ fallback: one-shot subprocess     └─ models cached by common.cached()
```

- `analyzers/runner.py` recognises commands of the form `<python> <dir>/<runner>.py ...` where `<dir>` also contains `worker.py`. It starts one worker per (interpreter, script) on first use, from the same interpreter as the configured command, so the API process still never imports torch.
- The worker calls the runner's own `main(argv)` and returns its JSON unchanged. Runners wrap model construction in `common.cached(key, load)`. Keys include the device and each weight file's path, size and modification time, so a replaced checkpoint is reloaded and its `checkpoint_id` is recomputed. `checkpoint_id()` and `revision()` are cached the same way.
- A worker serves one request at a time. Different detectors use different workers, so they run concurrently.
- A runner error is reported to the adapter as a failed subprocess, and the adapter fails closed with the same diagnostic. A timeout kills the worker. If a worker cannot start, refuses a connection or dies mid-request, it is stopped and that request runs once as an ordinary subprocess. The next request starts a fresh worker.
- Workers exit when the API process exits, so no orphaned process keeps holding GPU memory.
- The first upload after the API starts pays the model-loading cost once. Later uploads skip it.

Memory: each worker keeps its model resident. On a GPU, each also holds its own CUDA context, typically several hundred MB. The default stack runs 3 workers (face, whole-frame, audio). The all-model profile runs up to 7.

### Rules for runner authors

- `main(argv=None)` must call `parser.parse_args(argv)`. `tests/test_model_workers.py` enforces this.
- Put model and checkpoint loading inside `cached(...)`, and key it on every input that changes the loaded object (`file_key(...)` for files, plus device and repo).
- Cached objects must stay read-only. Create per-request state (for example `FaceCoverageTracker`) fresh on every call.
- Use `add_sys_path()` rather than `sys.path.insert`, and make any global monkey-patch idempotent (see `lfcc_compat.install`).

## Recommended AWS GPU host

Prices are approximate us-east-1 on-demand rates from November 2026. Check them in the AWS console, because they vary by region.

| Instance | GPU | vCPU / RAM | ~On-demand | Use it for |
| --- | --- | --- | --- | --- |
| **g6.xlarge** (recommended start) | NVIDIA L4, 24 GB | 4 / 16 GiB | ~$0.80/h | Default stack (EfficientNet + CommFor + AASIST) with `DEEPTRACE_MAX_PARALLEL_RUNNERS=4` |
| g6.2xlarge | NVIDIA L4, 24 GB | 8 / 32 GiB | check console | All-model profile, or if dlib face detection and FFmpeg (CPU-bound) dominate the profile |
| g4dn.xlarge | NVIDIA T4, 16 GB | 4 / 16 GiB | ~$0.53/h | Cheapest option. Older GPU with less memory; use `DEEPTRACE_MAX_PARALLEL_RUNNERS=3` |
| **g5.xlarge** (team's current host) | NVIDIA A10G, 24 GB | 4 / 16 GiB | ~$1.01/h | Default stack with `DEEPTRACE_MAX_PARALLEL_RUNNERS=4`. Use g5.2xlarge for the all-model profile |

Why g6.xlarge: 24 GB of GPU memory fits every default model as a warm worker with room to spare, the L4 is a current inference GPU, and it costs less than the g5. Upgrade to `g6.2xlarge` if you run the all-model profile, because 16 GiB of system RAM is tight once seven workers and TensorFlow (SOFTNet) are resident.

Keeping cost down:

- **Stop the instance when it is not in use.** You pay for the EBS volume only. Warm workers reload once on the next upload.
- **Spot instances** cost roughly half, but AWS can reclaim them. That is acceptable for demos, not for a shared review session.
- **Use a 100 GB gp3 root volume.** The CUDA image, model checkpoints and Docker build cache need the space.

### Setup

The deployment runbook for the team's g5.xlarge (quota, AMI, IAM role, S3, Bedrock, `.env.prod`, verification) is [AWS_DEPLOYMENT.md](AWS_DEPLOYMENT.md). The GPU is enabled from the env file: `COMPOSE_FILE=docker-compose.yml:docker-compose.gpu.yml`, `DEEPTRACE_TORCH_INDEX=cu126` and `DEEPTRACE_DEVICE=cuda`.

### Before relying on GPU scores

Thresholds and decision rules were set on CPU runs, and GPU arithmetic can differ in the last digits. Run several files whose CPU scores you already have, compare each component's `raw_score` and frame scores, and pay particular attention to any score near a threshold. Record the result before using the GPU host for review work.
