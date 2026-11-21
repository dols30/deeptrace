# Architecture notes

> Superseded for current behavior by [`docs/ARCHITECTURE.md`](../../docs/ARCHITECTURE.md). This page keeps the original PoC notes and AWS target. Detector scores are now reported independently, with no fusion.

## Current vertical slice

```text
Cognito Hosted UI -> browser PKCE token -> FastAPI token validation
Next.js frontend -> authenticated FastAPI upload -> bounded temporary file -> metadata/ffprobe
                                                |-> sampled frames -> selected video adapter
                                                |-> mono 16 kHz WAV -> selected audio adapter
                                                `-> unified advisory report
```

The API layer owns validation and lifecycle. Media extraction is isolated from inference. Each model implements `MediaAnalyzer`, allowing pretrained local models, SageMaker endpoints, or managed inference endpoints to be introduced without changing the report contract. The reporting layer combines only applicable scores and always preserves component status and limitations.

Authentication is optional locally and required in the intended AWS environment. Cognito owns credentials and sign-in; the browser uses Authorization Code with PKCE, and FastAPI verifies the RS256 signature, issuer, expiration, token type, and app-client ID. No passwords are handled or stored by DeepTrace.

## Implementation status

| Component | Status | Notes |
|---|---|---|
| Upload validation and size limit | Functional | Supported audio/video MIME allowlist |
| Temporary-file cleanup | Functional | Deleted after request unless explicitly configured |
| Hash/basic metadata | Functional | SHA-256, size, filename, media type |
| WAV extraction | Functional | Duration and PCM depth using Python standard library |
| General stream extraction | Functional with dependency | Uses `ffprobe`; emits warning if unavailable |
| Video preprocessing | Functional | Bounded frame sampling; selected video runner owns face alignment |
| Audio preprocessing | Functional | Extracts mono 16 kHz PCM from video |
| Video deepfake inference | Adapter ready | EfficientNet-B4 default; checkpoint/environment validation pending |
| Audio deepfake inference | Adapter ready | AASIST default; checkpoint/environment validation pending |
| Report generation | Functional | Missing/error models fail closed; detectors are reported independently with no fused score |

## AWS-friendly target

- Package the stateless API in the provided container and run on ECS/Fargate initially.
- Use API Gateway or an Application Load Balancer for ingress and authentication.
- For larger files, evolve to presigned S3 uploads plus an SQS-triggered worker; do not route large evidence through a synchronous API.
- Encrypt S3, queues, logs, and model artifacts with KMS; use least-privilege IAM roles and private networking.
- Store report/model version lineage separately from media. Define retention and deletion policies before handling sensitive material.
- Use CloudWatch metrics for latency, failures, score distributions, and model drift indicators. Never log raw media or sensitive filenames by default.
- CPU inference can begin on ECS; GPU-backed SageMaker asynchronous endpoints are a natural next step if selected models require acceleration.

## Model integration principles

Use pretrained, reproducible baselines and pinned model artifacts. Adapters return uncalibrated model scores, supported observations, model/version, preprocessing notes, and errors. Calibration and independent performance validation remain future work. Validate independently on public datasets such as FaceForensics++-style video corpora and ASVspoof audio corpora, subject to their licenses and access terms. Do not train from scratch in this PoC.

Fusion should not imply independence between signals. Begin with transparent weighted calibration on a held-out validation set, report per-modality evidence, and retain an abstain/manual-review state. Optimize and publish false-positive behavior rather than only aggregate accuracy.

Model choices, runner commands, and output contracts are maintained in [the model guide](models.md).
Report fields and guidance mapping are described in [reporting guidance](reporting-guidance.md).

## Frontend boundary

The `frontend/` directory is deployed independently. FastAPI serves JSON endpoints
only. Browser requests use `NEXT_PUBLIC_API_BASE_URL` at build time; CORS
allows only `DEEPTRACE_FRONTEND_ORIGINS`. Cognito callback/sign-out URLs point to
the frontend, not the API. Local ports are frontend 3000 and API 8000.

The Next.js App Router owns `/` and `/login/`. React components own upload,
preview, authentication state, and report rendering. A standalone frontend Docker
image runs independently of the Python API; model execution stays in FastAPI.
