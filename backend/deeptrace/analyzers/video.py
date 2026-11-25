from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from deeptrace.analyzers.base import MediaAnalyzer, command_args
from deeptrace.analyzers.runner import run_command
from deeptrace.ml.decision_rules import EFFICIENTNET_POC_RULE, EFFICIENTNET_RULES
from deeptrace.schemas import Anomaly, ComponentResult, MediaMetadata, ModelSample


class VideoCommandAnalyzer(MediaAnalyzer):
    """Shared frame subprocess protocol and result interpretation."""

    model_name: str
    command_setting: str
    # Face models score aligned crops and alert on any frame; whole-frame models alert on the
    # video-level mean because single compressed frames of real footage can cross the threshold.
    scores_faces = True
    # Face models alert per frame and report face coverage. Whole-frame models score every frame,
    # and single frames are too noisy to alert on, so they alert on the video-level mean instead.
    face_based = True
    detector_id = "face_detector"
    task = "face_manipulation"
    aggregation_method = "mean_aligned_face_frame_score"
    threshold = 0.5
    threshold_source = "default_model_decision_rule"

    def __init__(self, command: str | None, frame_interval_seconds: float = 1.0):
        self.command, self.interval = command, frame_interval_seconds
        self.last_profile = None

    def _runner_command(self, path: Path) -> list[str]:
        command_paths = {"frames_dir": path}
        if "{explain_dir}" in self.command:
            explain_dir = path.parent / "attribution"
            explain_dir.mkdir(parents=True, exist_ok=True)
            command_paths["explain_dir"] = explain_dir
        return command_args(self.command, **command_paths)

    def analyze(self, path: Path, metadata: MediaMetadata) -> ComponentResult:
        self.last_profile = None
        if not self.command:
            return ComponentResult(component="video", status="unavailable", model_name=self.model_name,
                model_version="unconfigured", detector_id=self.detector_id, task=self.task,
                notes=[f"Set {self.command_setting} after installing reviewed code and weights."])
        try:
            payload = json.loads(run_command(self._runner_command(path), timeout=900))
            self._validate_policy(payload)
            self.last_profile = payload
            scores = [float(item["fake_probability"]) for item in payload["samples"]]
            face_coverage = self._face_coverage(payload, len(scores)) if self.scores_faces else None
            if not scores:
                return ComponentResult(component="video", status="unavailable", model_name=self.model_name,
                    model_version=payload.get("model_version", "unpinned"), checkpoint=payload.get("checkpoint"),
                    detector_id=self.detector_id, task=self.task,
                    coverage=face_coverage,
                    notes=["No alignable faces were scored; no face-screening conclusion is available." if self.scores_faces else "No frames were scored; no generated-image screening conclusion is available.", *payload.get("notes", [])])
            if any(not 0 <= score <= 1 for score in scores):
                raise ValueError("invalid or empty scores")
            timestamps = []
            samples: list[ModelSample] = []
            explained = []
            for index, (item, score) in enumerate(zip(payload["samples"], scores)):
                match = re.fullmatch(r"frame_(\d+)\.jpg", item.get("path", ""))
                frame_index = int(match.group(1)) - 1 if match else index
                if frame_index < 0:
                    raise ValueError("Invalid frame index")
                start = frame_index * self.interval
                logits = item.get("logits")
                samples.append(ModelSample(
                    start_time=start, end_time=start + self.interval, raw_score=score,
                    raw_logits=logits if isinstance(logits, list) else None,
                    predicted_class="possible_manipulation" if score >= self.threshold else "no_elevated_signal",
                    score_scope="sample",
                ))
                if score >= self.threshold:
                    timestamps.append(start)
                raw_attribution = item.get("attribution")
                if isinstance(raw_attribution, dict) and raw_attribution.get("heatmap"):
                    explained.append({**raw_attribution, "start_time": start, "path": item.get("path"), "screening_score": score})
            attribution = None
            if explained:
                attribution = {
                    "method": "gradcam",
                    "modality": "video",
                    "target": "fake_logit_index_1",
                    "frames": explained,
                    "limitations": explained[0].get("limitations", []),
                }
            mean_score = sum(scores) / len(scores)
            if self.threshold_source == "default_model_decision_rule":
                mean_score = round(mean_score, 6)
            if self.scores_faces:
                anomalies = ([Anomaly(component="video", code="ELEVATED_FRAME_SCORE",
                    description="One or more face crops exceeded the provisional review threshold.", severity="medium")]
                    if timestamps else [])
            else:
                if mean_score < self.threshold:
                    timestamps = []
                anomalies = ([Anomaly(component="video", code="ELEVATED_GENERATED_SCENE_SCORE",
                    description="Whole-frame scores averaged above the provisional threshold for AI-generated imagery.",
                    severity="medium")] if mean_score >= self.threshold else [])
            coverage = len(scores) / len(payload["samples"]) if payload["samples"] else 0
            # The adapter only returns scored samples, so recover attempted coverage from its note when available.
            coverage_note = next((note for note in payload.get("notes", []) if note.startswith("Scored ")), "")
            match = re.match(r"Scored (\d+) of (\d+)", coverage_note)
            if match and int(match.group(2)):
                coverage = int(match.group(1)) / int(match.group(2))
            if face_coverage:
                coverage = face_coverage['frames_scored'] / face_coverage['frames_sampled']
            if self.scores_faces and coverage < 0.5:
                anomalies.append(Anomaly(component="video", code="LIMITED_FACE_COVERAGE",
                    description="Fewer than half of sampled frames contained an alignable face; the video score has limited coverage.",
                    severity="medium"))
            return ComponentResult(component="video", status="functional", model_name=self.model_name,
                model_version=payload.get("model_version", "unpinned"), checkpoint=payload.get("checkpoint"),
                synthetic_confidence=mean_score, anomalies=anomalies,
                timestamps_seconds=timestamps, samples=samples, attribution=attribution,
                coverage=face_coverage,
                detector_id=self.detector_id, task=self.task, raw_score=mean_score,
                calibrated_probability=None, threshold=self.threshold,
                threshold_source=self.threshold_source, threshold_validated=False,
                aggregation_method=self.aggregation_method,
                limitations=["The score is uncalibrated and is not a probability of manipulation."],
                notes=[*self._policy_notes(), f"Aggregated {len(scores)} face/frame scores by unweighted mean.",
                f"Highest sampled-frame score: {max(scores):.6f}.",
                "This frame model does not assess temporal consistency, blinking, or micro-expressions.", *payload.get("notes", [])])
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError, KeyError, ValueError, TypeError, AttributeError, IndexError) as exc:
            detail = getattr(exc, "stderr", None)
            diagnostic = f" Diagnostic: {detail.strip()[-1000:]}" if isinstance(detail, str) and detail.strip() else ""
            return ComponentResult(component="video", status="error", model_name=self.model_name,
                model_version="unknown", detector_id=self.detector_id, task=self.task,
                notes=[f"{self.model_name} adapter failed closed: {type(exc).__name__}.{diagnostic}"])

    def _validate_policy(self, payload: dict) -> None:
        pass

    @staticmethod
    def _face_coverage(payload: dict, scored: int) -> dict | None:
        coverage = payload.get('coverage')
        if coverage is None:
            return None  # Historical/third-party runners remain readable.
        keys = ('frames_sampled', 'frames_with_detected_face', 'frames_without_detected_face',
                'frames_with_unalignable_face', 'frames_scored')
        if (not isinstance(coverage, dict) or coverage.get('mode') != 'face_alignment_v1'
                or any(type(coverage.get(key)) is not int or coverage[key] < 0 for key in keys)):
            raise ValueError('Invalid face coverage')
        total, detected, absent, unaligned, count = (coverage[k] for k in keys)
        if (not total or detected + absent != total or count + unaligned != detected
                or count != scored or coverage.get('complete') is not (count == total)):
            raise ValueError('Inconsistent face coverage')
        return {key: coverage[key] for key in ('mode', *keys, 'complete')}

    def _policy_notes(self) -> list[str]:
        return []


class EfficientNetVideoAnalyzer(VideoCommandAnalyzer):
    model_name = "DeepfakeBench EfficientNet-B4"
    command_setting = "DEEPTRACE_EFFICIENTNET_COMMAND"
    detector_id = "deepfakebench_efficientnet_b4"

    def __init__(self, command: str | None, frame_interval_seconds: float = 1.0, *, explain: bool = False,
                 decision_rule: str = "default_0_5"):
        super().__init__(command, frame_interval_seconds)
        self.explain = explain
        self.decision_rule = decision_rule
        self.threshold, self.threshold_source = EFFICIENTNET_RULES[decision_rule]
        if decision_rule == EFFICIENTNET_POC_RULE and frame_interval_seconds != 1.0:
            raise ValueError("The FF++ c23 PoC rule requires a 1-second frame interval")

    def _validate_policy(self, payload: dict) -> None:
        if self.decision_rule != EFFICIENTNET_POC_RULE:
            return
        if (payload.get("model_version") != "efficientnetb4@f188b1c105465e2e5377eb536a95022ae0e4522d"
                or payload.get("checkpoint") != "effnb4_best.pth#sha256=74cbd82d7be1bf5e6adec717824274a95b4509b02e1e78401608d32b3cbeaf0f"
                or "Landmarks: shape_predictor_81_face_landmarks.dat#sha256=8cae4375589dd915d9a0a881101bed1bbb4e9887e35e63b024388f1ca25ff869" not in payload.get("notes", [])):
            raise ValueError("The FF++ c23 PoC rule requires the benchmark's checkpoint, source revision and landmarks")

    def _policy_notes(self) -> list[str]:
        if self.decision_rule != EFFICIENTNET_POC_RULE:
            return []
        return [f"PoC rule {self.decision_rule}: any aligned frame at or above {self.threshold!r} is flagged; the displayed score remains the frame mean.",
                "Threshold selected on a separate FF++ c23 development subset under a 5% false-positive cap. Small matched-domain benchmark only; not a validated DPS operational threshold."]

    def _runner_command(self, path: Path) -> list[str]:
        explain_dir = path.parent / "attribution"
        args = command_args(self.command, frames_dir=path, explain_dir=explain_dir)
        filtered: list[str] = []
        skip_next = False
        for arg in args:
            if skip_next:
                skip_next = False
                continue
            if arg == "--explain":
                continue
            if arg == "--explain-dir":
                skip_next = True
                continue
            if arg.startswith("--explain-dir="):
                continue
            filtered.append(arg)
        if self.explain:
            explain_dir.mkdir(parents=True, exist_ok=True)
            filtered.extend(["--explain", "--explain-dir", str(explain_dir)])
        return filtered


class EffortVideoAnalyzer(VideoCommandAnalyzer):
    """Effort frame adapter."""
    model_name = 'Effort + CLIP-L/14'
    command_setting = "DEEPTRACE_EFFORT_COMMAND"


class SceneVideoAnalyzer(VideoCommandAnalyzer):
    """Whole-frame AI-generated-content adapter (text-to-video, generated scenes)."""
    model_name = "Community Forensics ViT-S/384 (frontier fine-tune)"
    command_setting = "DEEPTRACE_SCENE_COMMAND"
    scores_faces = False
    detector_id = "community_forensics"
    task = "synthetic_video"
    aggregation_method = "mean_frame_score"


class CombinedVideoAnalyzer(MediaAnalyzer):
    """One video component from a face-manipulation model and a whole-frame generated-content model.

    The video score is the larger of the two component scores, so either kind of fake can raise
    concern; the false-positive rate is correspondingly the union of both models' false positives.
    """

    def __init__(self, face: VideoCommandAnalyzer, scene: SceneVideoAnalyzer):
        self.face, self.scene = face, scene
        self.model_name = f"{face.model_name} + {scene.model_name}"

    def analyze(self, path: Path, metadata: MediaMetadata) -> ComponentResult:
        face, scene = self.face.analyze(path, metadata), self.scene.analyze(path, metadata)
        face_notes = [f"Face model: {note}" for note in face.notes]
        scene_notes = [f"Whole-frame model: {note}" for note in scene.notes]
        if scene.status != "functional":
            return face.model_copy(update={"notes": [*face.notes,
                f"Whole-frame AI-generated-content screening was {scene.status}; only face manipulation was assessed.",
                *scene_notes]})
        if face.status != "functional":
            return scene.model_copy(update={"model_name": self.model_name, "notes": [
                f"Face model was {face.status}; the video score comes from whole-frame screening only.",
                *scene_notes, *face_notes]})

        by_time = {s.start_time: s for s in scene.samples}
        samples, face_won = [], set()
        for sample in face.samples:
            rival = by_time.pop(sample.start_time, None)
            if rival is None or sample.raw_score >= rival.raw_score:
                samples.append(sample)
                face_won.add(sample.start_time)
            else:
                samples.append(rival)
        samples = sorted([*samples, *by_time.values()], key=lambda s: s.start_time)

        attribution = face.attribution
        if attribution:
            # Grad-CAM explains the face model only; drop it where the scene model set the score.
            frames = [f for f in attribution.get("frames", []) if f.get("start_time") in face_won]
            attribution = {**attribution, "frames": frames} if frames else None

        return ComponentResult(component="video", status="functional", model_name=self.model_name,
            model_version=f"face={face.model_version}; scene={scene.model_version}",
            checkpoint=f"face={face.checkpoint or 'not reported'}; scene={scene.checkpoint or 'not reported'}",
            synthetic_confidence=max(face.synthetic_confidence, scene.synthetic_confidence),
            anomalies=[*face.anomalies, *scene.anomalies],
            timestamps_seconds=sorted({*face.timestamps_seconds, *scene.timestamps_seconds}),
            samples=samples, attribution=attribution,
            notes=[f"Video score is the maximum of the face-manipulation score ({face.synthetic_confidence:.6f}) "
                f"and the whole-frame AI-generated-content score ({scene.synthetic_confidence:.6f}).",
                "Per-sample scores show whichever model scored that frame higher.", *face_notes, *scene_notes])
