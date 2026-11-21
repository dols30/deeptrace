# Reporting guidance and scope

Report schema 0.2 records a unique report ID, UTC creation time, examination scope,
submitted-file metadata and complete SHA-256, processing methods, detector versions
and checkpoint hashes when supplied, component findings, summary, limitations and
pending human review. The web interface displays these fields and exports JSON.
No custody history, examiner identity, source assertion or certification is invented.

Reference mapping:

| Reference | Application | Boundary |
| --- | --- | --- |
| [SWGDE video 23-V-001-1.2, March 7 2024](https://www.swgde.org/wp-content/uploads/2024/03/2024-03-07-SWGDE-Best-Practices-for-Digital-Video-Authentication-23-V-001-1.2.pdf), draft cover; inconsistent 1.1 footer | File attributes, methodology, observations, interpretation and limitations | This is the proposal's cited edition, not a claim it is the latest approved guidance |
| [SWGDE audio 15-A-001 v1.3, September 20 2018](https://www.swgde.org/documents/published-complete-listing/15-a-001-swgde-best-practices-for-digital-audio-authentication/), approved | Scope, missing source context and constrained conclusions | No full audio authentication or source-device comparison |
| [LEVA Image and Video Authentication](https://www.leva.org/image-and-video-authentication/), accessed September 6 2026 | Metadata/content distinction and clear interpretation | Public educational objectives, not a normative report template or certification |

This is limited guidance alignment, not standards compliance or organizational
endorsement. The references are documentation guidance, not model-training data.
Each functional detector is reported independently. No cross-detector mean or
fused score is calculated (`overall_synthetic_confidence` is `null`). Partial
results explicitly disclose failed/unavailable components. Threshold observations
identify model concern and do not attribute blinking, noise, or other specific
artifacts that the models do not independently measure. Originality, source and
chain of custody remain outside this PoC. All conclusions require qualified review.
