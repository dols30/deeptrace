# Extended local PoC implementation

**November 11, 2026 update:** the user completed small Kaggle AASIST and EfficientNet benchmarks. The face rule selected on a separate development set (`ffpp_c23_kaggle_v1`, threshold `0.9967585206031799`) is now available in the explicit local PoC launcher and optional API setting. New face observations and workspace findings share that rule; the original audio and generated-image thresholds remain unchanged. The face test result was 93.75% accuracy, 2.5% FPR and 90% recall on 80 videos; the ordinary face 0.5 rule failed. This is small matched-domain evidence, not full acceptance. Details and recorded hashes: [model registry](MODEL_REGISTRY.md#development-selected-face-poc-rule--november-11-2026). The October implementation history below predates these runs.

October 22, 2026. This update implements additional analysis and reporting paths. It does **not** establish that every named PoC detection technique has been solved. Accuracy >=85% and FPR <10% are deferred at the user's request: the customer has no approved dataset yet, and the team will ask again at the next meeting. Public/synthetic media is currently used for functional testing only.

## Run locally

From `backend/`, using the API environment:

```sh
.venv/bin/python scripts/run_local_poc.py
```

This binds to 127.0.0.1:8000 (`PORT` can select another local port), opts into full AASIST windows, CNNDetection GAN-artifact screening, LFCC-LCNN spectral/vocoder-artifact screening, SOFTNet expression spotting and supplementary measurements. Credentials, authentication and ordinary model selectors are preserved. Install the optional assets/runtime as described in [models setup](../backend/docs/models.md). No new model is promoted into ordinary API defaults. The frontend API base must point at the selected local port.

For a restricted acceptance sandbox, configure real accounts/secret or Cognito and set `DEEPTRACE_DEPLOYMENT_MODE=sandbox`. Startup checks reject missing auth configuration, wildcard origins and external media assistants. These checks supplement network isolation, restricted provisioning and deployment review; they do not prove those controls are installed.

## Implemented in this update

| Area | Behavior |
| --- | --- |
| Learned GAN artifacts | Official CNNDetection ResNet-50 blur/JPEG checkpoint, strict weights, whole RGB frames, independent mean score and flagged sample timestamps when the mean crosses 0.5. This is artifact screening, not generator identification or pixel localization. |
| Learned spectral/vocoder artifacts | Official ASVspoof 2021 DF LFCC-LCNN checkpoint, strict weights and verified legacy FFT compatibility. Full-recording windows provide independent scores, raw bona-fide logits, coverage and flagged timestamps. No exact vocoder attribution. |
| Micro-expression spotting | Released SOFTNet CAS(ME)2 micro-expression fold s1 weights with authors' architecture, TV-L1 flow/strain preprocessing and adaptive peak spotting. Candidate intervals are technical review data, not synthetic-media decisions. Low frame rate, missing/multiple faces or unstable fixed crops abstain. |
| Audio duration | Optional full-recording AASIST coverage in consecutive 4.0375s windows. The final short window is repeat-padded; reported times exclude padding. Each flagged window remains visible even below a low overall within-detector mean. |
| Coverage | The report, workspace and PDF use actual decoded audio duration, analyzed duration, window count and completeness. Existing stored reports retain the legacy first-window notice. |
| Mel analysis | 64-band power spectrogram measurements with explicit FFT, hop, sample rate and band energies. |
| Spectral artifact review | Per-second spectral flatness/centroid measurements. No specific vocoder identification is asserted. |
| Background noise review | Within-block low-energy candidates and timestamped large level changes, with gain/environment/speech confounds stated. Too few low-energy blocks produces unavailable. |
| Eye/blink review | Dense eye-aspect-ratio measurements and candidate closure intervals. Face loss/cuts reset intervals; low frame rate or insufficient faces produces unavailable. |
| Facial movement | Normalized landmark displacement within continuous largest-face tracks. This does not classify micro-expressions. |
| Generated-image frequency review | Native decoded-frame FFT energy measurements alongside the existing independent generated-image detector. |
| Compression patterns | Native decoded-frame 8-pixel boundary contrast; the supplementary path does not re-encode JPEGs before measuring. |
| Format handling | All six PoC formats have real FFmpeg decoding/upload/report functional tests. Known extensions handle absent/octet-stream browser MIME. JPEG encoder full-range compatibility and very short clips are handled. |
| Failure reports | Video-preparation failure yields an incomplete report and lets the audio runner attempt original media. Detected-but-unextractable audio is an error, not falsely not-applicable. Storage errors preserve the current report response, label missing history/workspace/media and prompt a download. |
| Persisted evidence | Supplementary measurements and audio coverage round-trip through existing workflow JSON metadata; no DB column changes. Technical UI and PDF appendix include methods, values, intervals and limitations. |
| Interpretation | Numeric differences between unrelated face/image/speech tasks no longer create a new MODEL_DISAGREEMENT anomaly. Historical reports remain readable. No fused probability is calculated. |

`measured` means the statistic was computed, **not** that a manipulation was detected. Supplementary features never generate a synthetic-media decision. Exploratory relative eye-closure and noise-change rules are explicitly described, versioned and unvalidated. The supplementary runner defaults to the opening 30 seconds (CLI maximum 120), and each result records its actual coverage.

## What still requires a model, data, or external decision

| Gap | Current limit / next step |
| --- | --- |
| GAN artifact validation/localization | The trained artifact detector is integrated. Accuracy, calibration, individual artifact subtype and pixel localization are not established. The PoC does not require naming the generator architecture. |
| Biological interpretation of movement | Blink measurements and trained micro-expression interval spotting are integrated. They do not establish unnatural biology, emotion, deception or manipulation. SOFTNet requires suitable frame rate/face coverage and is limited to its recorded opening segment. |
| Compression history/tamper localization | Native block-grid statistics support review, but do not reconstruct codec history or localize edits. |
| Exact vocoder attribution | A dedicated trained LFCC-LCNN spectral-artifact path is integrated alongside AASIST and mel/noise measurements. It screens synthetic/converted-speech patterns; it does not name the vocoder. |
| Confidence/calibration | Scores remain uncalibrated. A fitted, versioned probability requires labeled calibration data distinct from held-out evaluation. Do not substitute raw-score averaging. |
| Accuracy and false positives | Deferred, not passed. No threshold was tuned against these functional fixtures. |
| 100% reporting / reasonable time | Failure handling and six-format tests are implemented, but total disk/network failure cannot promise saved retrieval. Agree eligible submissions and an acceptance time limit; measure representative inputs. |
| LEVA/SWGDE alignment | Structured file identity, methods, observations, interpretation, limitations and references are present. Qualified agency review/sign-off remains necessary; no certification or compliance claim is made. |
| Dataset approval, sandbox account provisioning and closeout | Obtain project-owner evidence at the next meeting. Meetings, approvals and showcase completion cannot be established by code. |

## Functional evidence

Tests use generated color bars/tones and a static public NASA astronaut portrait from bundled `skimage.data.astronaut`, combined with a generated tone. These are pipeline exercises, not representative forensic recordings or an approved validation set.

- Six actual file formats decode and produce saved reports with unconfigured detectors clearly unavailable.
- Nine-second tone/video input runs the real AASIST checkpoint in three windows through the end of the recording.
- The nine-second public-portrait fixture runs all three configured checkpoints, persists seven supplementary method records, and retrieves full-window coverage through the workspace API. One local run took about 21 seconds; this is not a general latency guarantee.
- No-face color bars abstain on face analysis; a static portrait supplies usable landmark frames. Insufficient block coverage produces an explicit unavailable noise result.
- Failure-path tests cover media preparation, media storage, unavailable runners, invalid coverage claims, legacy report compatibility and sandbox configuration.
- Generated JSON/PDFs and copied functional media remain under ignored `artifacts/`; no customer media, credentials, checkpoints or datasets are committed.

See [API contracts](API.md), [model/method registry](MODEL_REGISTRY.md), and the earlier [scope audit](DPS_SCOPE_REVIEW.md). Out-of-scope live DPS integration, custody systems, live streams and forensic certification have not been added.

Verification for this update: 94 backend tests passed (2 optional skips in the API environment), 2 numerical measurement tests passed separately in the model environment, and 66 frontend tests passed. Frontend typecheck/production build, backend compileall, model-runtime readiness and an actual three-checkpoint upload/persistence/retrieval smoke test passed. The numerical noise test checks a generated gain change across loud/quiet segments; the grid test compares an artificial 8-pixel pattern with a smooth ramp. The expanded 15-page functional PDF was rendered and visually reviewed, with no out-of-bounds text found. These checks establish implementation behavior, not detection accuracy or agency acceptance.

The subsequent artifact integration adds two optional independent detector results and one neural spotting record. Verification: 102 backend tests passed (four optional ML/numerical skips in the API environment); four numerical tests passed in the ML environment; 67 frontend tests, typecheck, production build, compileall and base model readiness passed. An actual three-second cropped static public-portrait/tone fixture ran all five detectors and all eight supplementary paths, saved/retrieved the workspace results, and took about21.4 seconds on this machine. SOFTNet also abstained on the uncropped multiple-face-detection fixture and low-frame-rate input. This is functional evidence only, not a benchmark. The current full technical PDF export was rendered/reviewed with its new artifact and expression records and no out-of-bounds text. Validation benchmarking is intentionally deferred, not recorded as passed. Even a movement candidate on a static fixture is not evidence of a genuine expression or of detection accuracy.
