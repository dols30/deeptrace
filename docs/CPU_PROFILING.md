# CPU inference profiling

DeepTrace emits one `DEEPTRACE PROFILE` log summary for every `POST /v1/analyze` request. The instrumentation uses only `time.perf_counter()` and the standard `logging` module. It does not alter model inputs, sampling, preprocessing, weights, thresholds, scores, or response schemas.

## Instrumented path

- `deeptrace/api.py`: upload/save, detector subprocess wall times, report construction, media copy, workflow database persistence, and legacy database persistence. A start line records logical CPU count and notes that the API process intentionally does not import PyTorch.
- `deeptrace/media.py`: the two independent FFmpeg subprocesses (sampled JPEG extraction and mono 16 kHz WAV extraction) plus workload metadata from the existing ffprobe call.
- `scripts/inference/efficientnetb4.py`: dependency imports, model/face-detector loading, JPEG reads, face detection/alignment, tensor preprocessing, and inference (or inference plus attribution when `--explain` is enabled).
- `scripts/inference/commfor.py`: dependency imports, model loading, image preprocessing, and inference.
- `scripts/inference/aasist.py`: dependency imports, model loading, audio decode/preprocessing, and inference (or inference plus attribution).

Detector wall times are parent timings measured by the API. Their indented runner stages are child timings and must not be added to the parent or to `TOTAL`. The gap between children and a detector parent includes Python process startup, argument/config parsing, JSON serialization, adapter validation/aggregation, and other small uninstrumented work. `TOTAL` is request wall time and includes cleanup and framework overhead.

The workload line reports values that are available without extra media passes: logical CPUs, duration, resolution, reported FPS, container frame count when ffprobe supplies it, sampled JPEG count, frames/faces actually analyzed, audio sample counts, model batch size, and PyTorch intra-op/inter-op thread counts. PyTorch is deliberately unavailable in the API environment; each model runner reports its own values instead. `frames_sampled` is the number written by FFmpeg. The profiler does not add a second decode merely to count every frame FFmpeg internally decoded; `frames_reported_by_container` is shown when the container exposes it.

## Run a benchmark

Start the configured API normally, then submit the same representative file on each instance:

```bash
curl -sS -o report.json -w 'HTTP %{http_code} total=%{time_total}s\n' \
  -H "Authorization: Bearer $DEEPTRACE_BENCHMARK_TOKEN" \
  -F 'file=@/path/to/benchmark.mp4;type=video/mp4' \
  http://127.0.0.1:8000/v1/analyze
```

When authentication is disabled, omit the authorization header. Capture backend logs and compare multiple warm and cold requests on each EC2 type. The current architecture starts each detector in a new subprocess, sequentially, so every request reloads all configured model checkpoints. Record that cold-loading cost rather than warming a separate persistent model process—the latter would be an architecture change.

Read the non-indented rows first to find the dominant request-level stage. Then inspect the indented child rows for the dominant detector. Compare workload counts before comparing timings, and compare PyTorch thread settings across hosts. Checkpoint `provenance hashing` is reported separately because the current runner computes a SHA-256 identifier on every invocation.

## Disable or remove

There is no runtime flag: profiling is deliberately small and always on for this measurement change. To remove it, delete `deeptrace/profiling.py`, remove the profiler calls in `deeptrace/api.py` and `deeptrace/media.py`, and remove the `profile`/`workload` additions from the three runner scripts. Those runner JSON keys are ignored by scoring logic and are not part of the HTTP API response.
