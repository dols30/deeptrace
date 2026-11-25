"""Subprocess boundary for descriptive PoC review measurements, not classifiers."""
import json
import math
import subprocess
from pathlib import Path

from pydantic import ValidationError

from deeptrace.analyzers.base import command_args
from deeptrace.analyzers.runner import run_command
from deeptrace.schemas import MediaMetadata, ReviewCheck

TECHNIQUES = {
    "gan_frequency": ("Generated-image frequency review", "video"),
    "blink": ("Eye closure and blinking", "video"),
    "facial_motion": ("Facial movement", "video"),
    "compression": ("Compression patterns", "video"),
    "mel_spectrogram": ("Mel-spectrogram analysis", "audio"),
    "vocoder": ("Spectral artifact review", "audio"),
    "background_noise": ("Background-noise consistency", "audio"),
}


def _invalid_constant(value):
    raise ValueError("Nonfinite runner output")


def empty_checks(metadata: MediaMetadata, status="unavailable", reason="Supplementary analysis is not configured."):
    return [ReviewCheck(technique=key, title=title, modality=modality,
        status="not_applicable" if metadata.media_kind == "audio" and modality == "video" else status,
        method="Not run", summary=reason,
        limitations=["This method does not establish authenticity or identify a specific generator."])
        for key, (title, modality) in TECHNIQUES.items()]


def analyze_review_signals(command: str | None, path: Path, metadata: MediaMetadata, timeout: int = 300) -> list[ReviewCheck]:
    if not command:
        return empty_checks(metadata)
    try:
        payload = json.loads(run_command(command_args(command, media_path=path), timeout=timeout),
            parse_constant=_invalid_constant)
        checks = [ReviewCheck.model_validate(item) for item in payload["checks"]]
        keys = [item.technique for item in checks]
        if len(keys) != len(set(keys)) or set(keys) != set(TECHNIQUES):
            raise ValueError("Runner must return each expected review method exactly once")
        for check in checks:
            if check.modality != TECHNIQUES[check.technique][1] or check.validated:
                raise ValueError("Invalid review modality or unsupported validation claim")
        return checks
    except (OSError, subprocess.SubprocessError, ValueError, TypeError, KeyError, ValidationError):
        return empty_checks(metadata, "error", "Supplementary analysis could not complete; no measurements are available.")


def analyze_micro_expression(command: str, path: Path, metadata: MediaMetadata, timeout: int = 900) -> ReviewCheck:
    base = dict(technique='micro_expression', title='Micro-expression intervals', modality='video',
        method='SOFTNet interval spotting', limitations=['Expression intervals do not establish manipulation or authenticity.'])
    if metadata.media_kind != 'video':
        return ReviewCheck(**base, status='not_applicable', summary='Video is required.')
    try:
        check = ReviewCheck.model_validate(json.loads(run_command(command_args(command, media_path=path),
            timeout=timeout), parse_constant=_invalid_constant))
        if check.technique != 'micro_expression' or check.modality != 'video' or check.validated:
            raise ValueError('Invalid spotting result')
        for value in check.measurements.values():
            if isinstance(value, (float, int)) and not math.isfinite(value):
                raise ValueError('Nonfinite measurement')
        for interval in check.intervals:
            if any(isinstance(value, (float, int)) and not math.isfinite(value) for value in interval.values()):
                raise ValueError('Nonfinite interval measurement')
            start, end = float(interval['start_time']), float(interval['end_time'])
            if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end):
                raise ValueError('Invalid spotting interval')
        return check
    except (OSError, subprocess.SubprocessError, ValueError, TypeError, KeyError, ValidationError):
        return ReviewCheck(**base, status='error', summary='Micro-expression spotting could not complete; no intervals are available.')
