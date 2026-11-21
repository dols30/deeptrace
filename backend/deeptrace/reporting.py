from deeptrace.schemas import AdvisoryReport, Anomaly, ComponentResult, MediaMetadata, ReviewCheck

REFERENCES = [
    {"organization": "SWGDE", "title": "Best Practices for Digital Video Authentication",
     "version": "23-V-001-1.2, 2024-03-07, draft (footer inconsistently says 1.1)",
     "url": "https://www.swgde.org/wp-content/uploads/2024/03/2024-03-07-SWGDE-Best-Practices-for-Digital-Video-Authentication-23-V-001-1.2.pdf",
     "application": "Separate file attributes, methods, observations, interpretation, and limitations."},
    {"organization": "SWGDE", "title": "Best Practices for Digital Audio Authentication",
     "version": "15-A-001 v1.3, 2018-09-20, approved",
     "url": "https://www.swgde.org/documents/published-complete-listing/15-a-001-swgde-best-practices-for-digital-audio-authentication/",
     "application": "State examination scope and missing original-source context; distinguish screening from authentication."},
    {"organization": "LEVA", "title": "Image and Video Authentication",
     "version": "Public course description, accessed 2026-09-06; not a normative report standard",
     "url": "https://www.leva.org/image-and-video-authentication/",
     "application": "Distinguish metadata and content assessment and clearly communicate interpretation."},
]
LIMITATIONS = [
    "A low score does not establish authenticity; a high score does not establish manipulation.",
    "Model softmax scores and their mean are uncalibrated, not probabilities that evidence is fake.",
    "Source device, original-recording status, acquisition history, and asserted events were not verified.",
    "SHA-256 identifies the received file bytes only; it does not establish provenance or chain of custody.",
    "No forensic certification, chain-of-custody tracking, or LEVA/SWGDE endorsement is provided.",
    "Supplementary eye, motion, frequency, compression-grid, mel and low-energy measurements support review; they do not establish manipulation. Optional micro-expression spotting identifies candidate movement intervals, not emotion or deception. Exact GAN/vocoder attribution and compression-history reconstruction are not provided.",
]

DISCLAIMER = (
    "DeepTrace outputs are AI-assisted indicators intended to support investigator review. "
    "A flagged result does not establish that media is manipulated, and a non-flagged result "
    "does not establish authenticity."
)


def build_report(media: MediaMetadata, components: list[ComponentResult], *, processing_methods: list[str] | None = None,
                 review_checks: list[ReviewCheck] | None = None,
                 keep_uploads: bool = False, visual_weight: float = 0.5) -> AdvisoryReport:
    scored_components = [c for c in components if c.status == "functional" and c.synthetic_confidence is not None]
    scored = [c.synthetic_confidence for c in scored_components]
    # These detectors answer different forensic questions. Until a fusion model
    # is trained and validated, a mathematical overall score is misleading.
    overall = None
    anomalies = [a for component in components for a in component.anomalies]
    # Unrelated tasks are not competing estimates of the same event. A numerical
    # score difference between face/image/speech models is not an anomaly.
    anomalies.extend(Anomaly(component="media", code="METADATA_WARNING", description=w, severity="low")
                     for w in media.extraction_warnings)
    if any(c.status == "stub" for c in components):
        summary = "The media was processed successfully, but one or more detection components are placeholders; no authenticity conclusion can be drawn."
        action = "Use this result to test workflow integration only. Do not use the placeholder score for case decisions."
    elif not scored:
        summary = "No applicable detector produced a score."
        action = "Confirm the media format and request qualified technical review."
    else:
        elevated = [c.model_name for c in scored_components if any(a.code.startswith('ELEVATED_') for a in c.anomalies)]
        summary = ("Synthetic/manipulation indicators were detected in: " + ", ".join(elevated) + "."
            if elevated else "No detector produced an elevated indicator under its development/default decision rule.")
        summary += " These are independent, uncalibrated model scores and must be reviewed with the media."
        action = "Review each detector and its evidence independently; seek corroborating evidence and qualified human review."
    incomplete = [c.model_name for c in components if c.status in {"unavailable", "error"}]
    if scored and incomplete:
        summary += " Screening is incomplete: " + ", ".join(incomplete) + " produced no result."
    methods = ["SHA-256 calculated on received upload; basic metadata extraction with warnings recorded.",
        *(processing_methods or []),
        "Detector scores are reported independently; no cross-detector average or fusion score is calculated.",
        "Each detector's recorded development/default decision rule is not a validated DPS operational threshold."]
    methods.extend(f"{c.component}: {c.model_name} ({c.model_version}); status={c.status}; checkpoint={c.checkpoint or 'not reported'}" for c in components)
    methods.extend(f"Supplementary {c.title}: {c.method}; version={c.version}; status={c.status}; not a validated classifier."
        for c in review_checks or [])
    return AdvisoryReport(integrity={"hash_algorithm": "SHA-256", "received_file_hash": media.sha256,
        "provenance": "Not established", "custody": "Not tracked (outside PoC scope)",
        "upload_retention": "Configured to retain upload" if keep_uploads else "Upload scheduled for deletion at request completion"},
        methods=methods, limitations=list(LIMITATIONS), references=REFERENCES,
        disclaimer=DISCLAIMER, media=media, overall_synthetic_confidence=overall,
        evidence_summary=[{"task": c.task, "detector_id": c.detector_id, "model_score": c.raw_score,
            "calibrated_probability": c.calibrated_probability, "threshold": c.threshold,
            "threshold_validated": c.threshold_validated, "status": c.detector_status}
            for c in components],
        summary=summary, anomalies=anomalies, components=components, review_checks=review_checks or [], recommended_action=action)
