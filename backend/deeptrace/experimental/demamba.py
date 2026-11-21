from pathlib import Path

from .models import ExperimentalDetectorResult


class DeMambaAdapter:
    """Explicit blocker for the official DeMamba release.

    As of the audit date the official repository does not publish a compatible
    pretrained detector checkpoint or a complete single-video inference path.
    """
    detector_id = "demamba"
    detector_name = "DeMamba"
    task = "synthetic_video"

    def __init__(self, repository: Path | None = None, checkpoint: Path | None = None):
        self.repository, self.checkpoint = repository, checkpoint

    def predict_video(self, path: Path) -> ExperimentalDetectorResult:
        return ExperimentalDetectorResult(detector_id=self.detector_id, detector_name=self.detector_name,
            task=self.task, status="blocked", model_version="official-checkpoint-unavailable",
            checkpoint=str(self.checkpoint) if self.checkpoint else None,
            error="DeMamba: BLOCKED — the official release does not provide a reproducible pretrained detector checkpoint and single-video inference contract.",
            limitations=["EXPERIMENTAL — NOT USED FOR FINAL DEEPTRACE ASSESSMENT."])
