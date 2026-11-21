# DPS proof of concept scope review

**Current update:** extended local implementation and remaining scientific limitations are documented in [POC_IMPLEMENTATION.md](POC_IMPLEMENTATION.md). The original audit below describes the baseline before those additions. Accuracy/FPR acceptance is now deferred by the user pending the next dataset discussion.

The local profile now includes dedicated CNNDetection GAN-artifact and LFCC-LCNN spectral/vocoder-artifact detectors, full-recording audio windows, blink/compression/mel/noise measurements, and pretrained SOFTNet micro-expression interval spotting. These persist and export with their method/coverage/provenance. Rows below labeled missing describe the historical baseline, not the current local profile. Detection performance, calibration and operational acceptance remain unverified; exact generator/vocoder attribution is not required by the supplied scope and is not claimed.

Reviewed the full supplied document, “DPS AI-Enabled Deepfake Detection Tool PoC DeepTrace,” scope dated June 8, 2025, including its tables and review comments. This review maps the scope to the implementation; it does not assert DPS acceptance or LEVA/SWGDE certification.

| Scope requirement | Current implementation and remaining work |
| --- | --- |
| MP4, MOV, AVI, MP3, WAV, M4A upload | Upload control and API MIME allowlist support all six formats. FFmpeg probes and prepares media. Uploads are capped at 100 MB. |
| Video screening | Independent face manipulation (EfficientNet-B4) and whole-frame generated imagery (Community Forensics) checks. Face coverage depends on alignment; whole-frame analysis uses still-image crops. No validated blinking, micro-expression, temporal consistency, or compression-artifact localization capability. |
| Audio screening | AASIST screens the first 64,600 samples at 16 kHz (4.0375 seconds). It provides a speech anti-spoofing signal. Long-recording coverage and distinct background-noise/vocoder anomaly explanations are not established. |
| Structured report and plain-language summary | Existing JSON and PDF reports include independent detector results, observations, summaries, methods, SHA-256, limitations, and advisory language. Investigator edits and supervisor review are available. |
| Scope terminology “confidence score” | Implemented as an uncalibrated model score for each detector. No probability, fused score, or authenticity determination is justified. Calibration requires a fitted, versioned procedure and validation data. |
| Authorized sandbox access | Backend JWT authentication and role checks enforce access when authentication is enabled; base local settings default it off. Local Docker uses employee credentials and PostgreSQL. Production deployment and external access remain outside the scope. |
| Public or synthesized data | Upload UI and homepage now state this restriction. This is a usage instruction; the app cannot establish whether an uploaded recording meets it. Do not use actual case evidence for this PoC. |
| 85% accuracy and under 10% false positive rate | Acceptance targets, not demonstrated results. Benchmark tooling exists, but this review has no approved representative labeled validation set or signed-off evaluation establishing either target. Freeze checkpoints, preprocessing, independent sample units, and splits before evaluating. Report each detector separately with coverage and sample counts. |
| Reports for every submitted file | Successful accepted analysis produces a report even if a detector returns an error or is unavailable. Unsupported files and oversized uploads return errors; media-preparation and persistence failures can still prevent report creation. The 100% target is not established. Define accepted-submission handling, failures, and processing-time limits before acceptance testing. |
| LEVA and SWGDE alignment | Reports contain integrity and limitation documentation and references. Formal review of the applicable published guidance and terminology by qualified reviewers is still needed. References and SHA-256 do not establish standards compliance, chain of custody, or admissibility. |
| Closeout and validation | The source document leaves dates and SME availability unresolved, and asks for SWGDE material. Confirm approved datasets, reviewer availability, applicable document editions, and the acceptance protocol with the project owners. |

Changes from this review: distinguish the explicitly labeled homepage example from actual case results; improve readable system typography and display scaling; retain advisory language; make guidance opt-in; display the configured whole-frame detector alongside the face and speech detectors; show an attribution score only from its matching detector; render the audio waveform at the display’s pixel density. No detectors, checkpoints, thresholds, preprocessing, database tables, or authorization rules were changed.

Chain-of-custody systems, evidence-management integration, live-stream analysis, forensic certification, and live DPS deployment remain explicitly out of scope. They should not be added merely to complete a feature checklist.

## Agency usability feedback

Analysis now opens on an Officer summary with a plain-language result, separate check outcomes, screened-coverage limitations, next steps, flagged timestamps, and investigator assessments. Technical details holds independent model scores, development thresholds, calibration status, versions, processing notes, SHA-256, attribution, and the original automated draft. Failed or missing checks are labeled incomplete, never a clear result. Flagged individual frames remain visible even when their detector average is below the rule.

This addresses the requested separation of officer guidance from technical material. It does not satisfy a binary authenticity determination: the supplied DPS scope explicitly defines outputs as advisory, and neither calibration nor the acceptance targets have been demonstrated. A no-flag result cannot establish authenticity. Officers and the named project validators still need to review the wording and complete acceptance testing.

## Detailed in-scope audit - October 22, 2026

**The full PoC scope is not yet complete.** This is a source-code and report-export review against the supplied June 8, 2025 PoC, sections 2.1 and 2.3. It does not establish model accuracy, runtime readiness, deployment controls, or agency acceptance.

| Requirement | Status | Implementation evidence and remaining work |
| --- | --- | --- |
| MP4, MOV, AVI, MP3, WAV, M4A uploads and result retrieval | Implemented in code | Screening upload control, media MIME allowlist, FFmpeg preparation, analyze and saved-report API routes. Acceptance tests with real files of each format remain necessary. |
| GAN artifact analysis | Partial | Community Forensics performs whole-frame generated-image screening. A separately validated GAN-artifact finding or artifact classification/localization is not implemented. |
| Facial-region inconsistency detection | Partial | EfficientNet-B4 screens aligned face crops and returns scores, flagged timestamps, and coverage. Specific inconsistency types and operational performance are not established. |
| Unnatural blinking / micro-expression anomalies | Not implemented as a detector | The video adapter explicitly states that the frame model does not assess temporal consistency, blinking, or micro-expressions. Attribution overlays do not implement these checks. |
| Compression artifact patterns | Not implemented as a detector | Codec/container metadata and compression-shift evaluation plans exist; a dedicated compression-artifact detector is not present in the selected screening path. |
| Mel-spectrogram analysis | Not separately implemented in the selected baseline | The AASIST runner passes a raw mono waveform to the model. Waveform or spectral attribution is not the explicit mel-spectrogram workflow named in the PoC. |
| Vocoder artifact identification | Not implemented as a separate finding type | AASIST supplies a spoofing score; its adapter does not identify or describe a particular vocoder artifact. |
| Voice-synthesis pattern detection | Partial | Pretrained speech anti-spoofing is present. AASIST screens the opening 64,600 samples at 16 kHz (4.0375 seconds); shorter input is repeat-padded. Full-recording coverage and specific synthesis-pattern explanations remain gaps. |
| Background-noise inconsistency flagging | Not implemented as a detector | No dedicated detector or anomaly type establishing noise inconsistency was found in the selected pipeline. |
| Structured report per analyzed file | Implemented for successful processing | JSON, saved-report views, and downloadable PDF. The revised export separates an officer overview, detector evidence, and an examination record. Processing/persistence failures can still prevent a report. |
| Confidence score / assessment | Partial; validation required | Independent raw model scores and a plain-language advisory result exist. Selected adapters leave calibrated probability unset. The PoC does not specify score fusion; averaging unrelated uncalibrated scores would not resolve the scientific gap. Agree the intended assessment and validation protocol with the named validators. |
| Anomaly descriptions and non-technical summary | Implemented for supported model signals | Overview and PDF use shared result logic and preserve incomplete/demo states. Supported flags do not substitute for the specific missing anomaly types above. Agency usability and wording acceptance are not established. |
| LEVA/SWGDE report structure and terminology | Partial; qualified review required | File identification/SHA-256, methods, observations, interpretation, limitations, and references are included. References do not prove conformance, endorsement, or forensic certification. |
| Authorized DPS access in a sandbox | Implemented capability; configuration-dependent | API routes use require_user; Docker Compose enables authentication. Base settings default authentication off for local development. Verify provisioning, roles, restricted access, and authentication in the actual acceptance environment. |

### Acceptance targets

| Target | Result of this review |
| --- | --- |
| Detection accuracy of at least 85% | Not verified. Evaluation and benchmark tooling exist; no approved held-out evaluation establishing this target was identified in the reviewed tracked source. |
| False positive rate below 10% | Not verified. Requires representative labeled authentic recordings, frozen thresholds, source-independent splits, and reported confusion counts. |
| Reports for 100% of submitted files within a reasonable processing window | Not verified. Upload-size, media-format, preprocessing, and persistence failure paths exist. Define eligible submissions and the time limit, then measure completion and failures. |
| Required advisory, score, and anomaly fields in every report | Partially supported. Successful report contracts include the fields; missing scores are reported as unavailable. Validate error paths and final terminology with qualified reviewers. |
| Approved public/synthesized datasets and representative validation | Not established by code. Instructions and benchmark tools do not demonstrate approval, representativeness, or completed evaluation. |
| Kickoff, access verification, literature review, benchmarking/refinement, closeout, repository finalization, and showcase | Requires project evidence. Code cannot establish meetings, SME sign-off, acceptance, closeout documents, or presentation completion. |

### Completion priorities

1. Obtain written agreement on which named detection techniques remain mandatory within the time-bounded PoC.
2. Implement and validate the missing required checks, or record approved scope changes explicitly.
3. Define and validate the file-level advisory/confidence assessment without inventing a combined probability.
4. Evaluate frozen models and preprocessing on approved labeled data; report accuracy, FPR, coverage, and failure counts.
5. Test report completion and processing time across eligible formats and failure scenarios.
6. Obtain qualified review of the report terminology, sandbox controls, and acceptance evidence.

Implementation references: backend/deeptrace/api.py; backend/deeptrace/media.py; backend/deeptrace/auth.py; backend/deeptrace/config.py; backend/deeptrace/analyzers/video.py; backend/deeptrace/analyzers/audio.py; backend/scripts/inference/aasist.py; backend/deeptrace/ml/evaluation.py; backend/scripts/benchmark.py; backend/docs/evaluation.md; frontend/components/screening.tsx; frontend/lib/report-pdf.ts; docker-compose.yml.

Production use, DPS systems integration, live streams, forensic certification, and chain-of-custody systems remain out of scope.
