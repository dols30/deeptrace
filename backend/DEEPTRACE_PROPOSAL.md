# AI Innovation Hub: DeepTrace Proposal

## Team Information

**Team Members:** Dol Raj Bashyal, Krish Karki, Tarbi Pyakurel  
**Team Name:** Silicon Peaks  
**Institution:** University of Southern Mississippi  
**Date:** September 07, 2026

### Team Member Bios

**Dol Raj Bashyal** is a CS major senior with a minor in mathematics and economic data analysis. He has prior experience working across web products (full-stack applications), cross-platform applications, native applications, databases, cloud infrastructure, and security research. He is interested in integrating machine learning techniques into application development.

GitHub: [dols30](https://github.com/dols30)

**Krish Karki** is a junior at the University of Southern Mississippi, majoring in computer science with a minor in economic data analysis. He has prior experience in full-stack development, working with technologies such as Java and Spring Boot, and currently focuses on data analysis, machine learning, and developing smart applications with AI-embedded features. He plans to combine his academic and development background with his interest in ML and AI to continue building real-world, full-stack AI projects.

GitHub: [Kirishdai](https://github.com/Kirishdai)

**Tarbi Pyakurel** is a senior at the University of Southern Mississippi majoring in computer science and minoring in economic data analysis. His academic background combines software development with data analysis. He is currently working on AI security projects.

GitHub: [tarbipyakurel21](https://github.com/tarbipyakurel21)

## Agency / Problem Area

**DPS AI-Enabled Deepfake Detection Tool (DeepTrace)**

## 1. Problem Understanding & Strategic Alignment

### Agency Problem Description

The Mississippi Department of Public Safety (DPS) personnel regularly work with body camera footage, surveillance recordings, recorded interviews, and other forms of digital evidence submitted in criminal cases. They currently rely on manual inspection and referrals to external forensic specialists. The spread of AI-generated synthetic media, commonly referred to as deepfakes, presents an extra challenge for DPS personnel.

### Why This Problem Matters

Time-consuming manual reviews can delay investigations and may produce inconsistent results, especially in cases where deepfakes are used. A screening tool that highlights possible signs of manipulation could help personnel identify files that need closer expert review.

## 2. Proposed AI-Enabled Solution

### Solution Overview

Our proposal is to develop DeepTrace, a Proof of Concept (PoC) application that analyzes uploaded video and/or audio for indicators of synthetic manipulation. It will extract media metadata, send audio and video streams to separate pretrained or finetuned detection components, and assemble their independent outputs into a structured report that includes separate, uncalibrated model scores, a list of detected anomalies with descriptions, and a plain-language summary for non-technical investigators. The scores are screening signals, not probabilities or a fused confidence value. Report structure and terminology will be informed by LEVA material on video authentication and SWGDE guidance for digital evidence documentation; this is not a claim of standards compliance or endorsement.

### Key Features & Functionality

- Web-based interface for file upload and result retrieval
- Accessible to authorized DPS personnel in a sandboxed environment
- Upload audio and video files in common law enforcement formats (MP4, MOV, AVI, MP3, WAV, M4A)
- Extract relevant media metadata for the unified report
- Analyze video for potential signs of synthetic or manipulated content that may include facial region inconsistency, unnatural blinking, compression artifact, and micro-expression anomalies using pretrained and/or adapted detection models
- Analyze audio for potential voice synthesis, spoofing, and background noise inconsistency using pretrained and/or adapted detection models
- Current implementation status: the production detectors screen aligned face crops, sampled frames for generated imagery, and speech for spoofing. They do not independently detect blinking, micro-expressions, temporal or compression inconsistencies, specific vocoder artifacts, or background-noise inconsistencies. These remain unmet PoC goals pending model selection and validation; do not describe their outputs as detected anomalies.
- Provide separate, uncalibrated model scores and a list of detected anomalies with descriptions
- Report structure and terminology aligned with LEVA standards for video authentication and SWGDE guidelines for digital evidence integrity documentation
- Generate a structured, plain-language summary for non-technical investigators

### Innovation Statement

DeepTrace combines multiple forms of media analysis in one authenticated, web-based, transparent screening workflow. Its value is not simply producing a score, but it shows which component produced the result and explains findings in language that nontechnical users can also understand.

## 3. Impact Potential and Scalability

### Expected Benefits

- Support faster preliminary screening of submitted audio and video for potential signs of manipulation
- Help investigators prioritize media that may require additional forensic examination
- Provide a consistent and repeatable process for documenting automated analysis results
- Clear communication of uncertainty and model limitations

### Replicability & Scalability Potential

This system can be replicated and evaluated by multiple agencies responsible for public safety. Web-based interfaces can be useful in scaling. This PoC will deliver a reusable research foundation, not a statewide production service.

## 4. Feasibility & Technical Approach

### Technical Feasibility

This project is feasible within the Innovation Hub timeline because the team will integrate pretrained models rather than build deepfake detectors from scratch. Week 2 candidates for audio models are AASIST or Nes2Net, which are evaluated with the ASVspoof dataset. Candidates for the video model are the FaceForensics++-trained EfficientNet-B4 baseline through DeepfakeBench for sampled video-face analysis. These are candidates, not final selections. Sample video recordings and audio recordings provided by Mississippi DPS will be used by synthesizing or de-identifying for training and validation.

### Additional Data Requirements

Development and testing will use approved publicly available labeled datasets if training or fine-tuning is required. FaceForensics++ for video datasets and ASVspoof-style audio datasets may be used for model training or benchmarking. Before use, the team will document each dataset's source, license, labels, sensitive-content considerations, and train/validation/test separation. Publicly available documentation such as LEVA and SWGDE will be used as a guideline for model training.

## 5. Project Scope Statement

### In Scope

- Accept uploaded audio and video files in common law enforcement formats (MP4, MOV, AVI, MP3, WAV, M4A) and use candidate models to apply both audio and video-based techniques to perform automated deepfake detection analysis
- Produce a structured report for each file analyzed, informed by LEVA and SWGDE guidance, with separate uncalibrated model scores, a list of detected anomalies with descriptions, and a plain-language summary for non-technical investigators; this is not a claim of standards compliance
- Web-based interface for file upload and deepfake analysis result retrieval that is accessible to authorized DPS personnel in a sandboxed environment

### Out of Scope

Production deployment or live investigative use; integration with DPS case, evidence, or records systems; legally admissible forensic certification; chain-of-custody tracking or evidence handling; real-time or live-stream analysis; external access; and detection of every possible manipulation technique are outside this PoC.

## 6. Timeline & Work Plan

### Original Timeline & Work Plan

| Week Number | Deliverables | Planned Start Date |
|---|---|---|
| Week 1 | Kickoff and access verification; confirm scope and approved data/media sources | TBD |
| Week 2 | Environment setup; exploration of audio/video analysis models and deepfake detection techniques (GAN artifact detection, frequency analysis, biological signal inconsistency); LEVA and SWGDE documentation review | TBD |
| Week 3 | Integration of detection model(s) for video analysis; frame-level and facial-region assessment; independent model-score output | TBD |
| Week 4 | Audio analysis module development; mel-spectrogram and vocoder artifact detection; voice synthesis pattern identification; unified report generation | TBD |
| Week 5 | Accuracy benchmarking against the labeled test set; refinement based on feedback | TBD |
| Week 6 | Closeout documents; GitHub repo finalization | TBD |
| Week 7 | Final presentation at Showcase | TBD |

### Team Proposed Timeline

Proposed start dates are subject to Hub and DPS. The original agency milestones above are retained.

| Week Number | Deliverables | Planned Start Date |
|---|---|---|
| Week 1 | Kickoff and access verification; confirm scope and approved data/media sources | 09/15/26 |
| Week 2 | Environment setup; exploration of audio/video analysis models and deepfake detection techniques (GAN artifact detection, frequency analysis, biological signal inconsistency); LEVA and SWGDE documentation review | 09/22/26 |
| Week 3 | Integration of detection model(s) for video analysis; frame-level and facial-region assessment; independent model-score output | 09/29/26 |
| Week 4 | Audio analysis module development; mel-spectrogram and vocoder artifact detection; voice synthesis pattern identification; unified report generation | 10/06/26 |
| Week 5 | Accuracy benchmarking against the labeled test set; refinement based on feedback | 10/13/26 |
| Week 6 | Closeout documents; GitHub repo finalization | 10/20/26 |
| Week 7 | Final presentation at Showcase | 10/27/26 |

## 7. Team Collaboration & Readiness

### Team project roles & responsibilities

**Dol Raj Bashyal (Application & Cloud Integration):** Develop the web interface, media upload and validation workflow, AWS sandbox integration, benchmark design, error analysis, and connect analysis outputs to the unified report.

**Krish Karki (Audio Analysis & Evaluation):** Explore and integrate candidate audio deepfake models, support audio preprocessing and ASVspoof-based evaluation, and produce separate uncalibrated audio model scores and anomaly outputs.

**Tarbi Pyakurel (Video Analysis & ML Evaluation):** Explore and integrate candidate video deepfake models, support frame/facial-region preprocessing and FaceForensics++-based evaluation, and produce separate uncalibrated video model scores and anomaly outputs.

### Shared Responsibilities

Collaborate on model selection, LEVA/SWGDE-aligned reporting, system integration, testing, documentation, GitHub finalization, and the final showcase presentation.

### Requested support

- Appropriate access to DPS training datasets
- Guidance on acceptable synthesized public datasets and relevant media-forensics standards
- AWS sandbox access and AWS Skill Builder resources

## 8. Ethical, Legal, Privacy & Security Considerations

### Risks or Concerns

- False positives and false negatives may lead to incorrect interpretation of screening results
- Limited experience with AWS may create challenges in configuring access controls and managing uploaded data

### Mitigation Plan

- Clearly label all results as advisory and require qualified human interpretation. A low manipulation score does not establish authenticity, and a high score does not prove manipulation
- Use AWS training resources and agency technical guidance to verify sandbox configuration and access controls

## 9. Additional Notes

The team is prepared to iterate quickly based on evaluation and feedback and try different candidate models or finetune candidate models until the accuracy threshold is reached.

### Selected technical resources and scope basis

- **Candidate models:** AASIST / AASIST-L; DeepfakeBench / EfficientNet-B4
- **Benchmarks:** FaceForensics++; ASVspoof 2021
- **Forensic terminology:** SWGDE video (23-V-001 v1.2); SWGDE audio (15-A-001 v1.3); LEVA
- **Hosting:** ITS AWS sandbox; S3 public-access controls; SageMaker private-network guidance

Living implementation docs for the codebase are maintained under `docs/` (architecture, models, reporting, roadmap, evaluation). This file is the Hub submission proposal.
