from __future__ import annotations

import hashlib
import json
import subprocess
import wave
import shutil
import tempfile
from time import perf_counter
from pathlib import Path

from deeptrace.schemas import MediaMetadata

ALLOWED_TYPES = {
    "audio/wav": "audio", "audio/x-wav": "audio", "audio/mpeg": "audio",
    "audio/mp4": "audio", "audio/x-m4a": "audio", "audio/flac": "audio",
    "video/mp4": "video", "video/quicktime": "video", "video/x-msvideo": "video",
    "video/avi": "video", "video/x-matroska": "video", "video/webm": "video",
}
FALLBACK_TYPES = {".mp4":"video/mp4", ".mov":"video/quicktime", ".avi":"video/x-msvideo",
    ".mp3":"audio/mpeg", ".wav":"audio/wav", ".m4a":"audio/mp4"}


def classify_media(content_type: str) -> str:
    if content_type not in ALLOWED_TYPES:
        raise ValueError(f"Unsupported media type: {content_type or 'unknown'}")
    return ALLOWED_TYPES[content_type]


def extract_metadata(path: Path, filename: str, content_type: str, ffprobe_path: str,
                     workload: dict | None = None,
                     timings: dict[str, float] | None = None) -> MediaMetadata:
    if content_type in {"", "application/octet-stream"}:
        content_type = FALLBACK_TYPES.get(Path(filename).suffix.lower(), content_type)
    kind = classify_media(content_type)
    started = perf_counter()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if timings is not None:
        timings["upload SHA-256"] = perf_counter() - started
    duration = None
    container = path.suffix.lower().lstrip(".") or None
    codecs: list[str] = []
    warnings: list[str] = []

    if content_type in {"audio/wav", "audio/x-wav"}:
        try:
            with wave.open(str(path), "rb") as wav:
                duration = wav.getnframes() / wav.getframerate()
                codecs = [f"pcm-{wav.getsampwidth() * 8}"]
        except (wave.Error, EOFError) as exc:
            warnings.append(f"WAV metadata could not be read: {exc}")

    started = perf_counter()
    try:
        result = subprocess.run(
            [ffprobe_path, "-v", "error", "-show_entries",
             "format=duration,format_name:stream=codec_type,codec_name,width,height,avg_frame_rate,nb_frames",
             "-of", "json", str(path)], capture_output=True, text=True, timeout=15, check=True,
        )
        probe = json.loads(result.stdout)
        fmt = probe.get("format", {})
        duration = float(fmt["duration"]) if fmt.get("duration") else duration
        container = fmt.get("format_name", container)
        codecs = [f"{s.get('codec_type')}:{s.get('codec_name')}" for s in probe.get("streams", [])]
        if workload is not None:
            workload["duration_seconds"] = duration
            video = next((s for s in probe.get("streams", []) if s.get("codec_type") == "video"), None)
            audio = next((s for s in probe.get("streams", []) if s.get("codec_type") == "audio"), None)
            if video:
                workload["resolution"] = f"{video.get('width')}x{video.get('height')}"
                workload["fps"] = video.get("avg_frame_rate")
                if video.get("nb_frames") not in (None, "N/A"):
                    workload["frames_reported_by_container"] = video["nb_frames"]
            if audio:
                workload["audio_duration_seconds"] = duration
    except (FileNotFoundError, subprocess.SubprocessError, json.JSONDecodeError, ValueError) as exc:
        warnings.append(f"ffprobe metadata unavailable: {type(exc).__name__}")
    finally:
        if timings is not None:
            timings["media probe"] = perf_counter() - started

    return MediaMetadata(filename=filename, media_kind=kind, content_type=content_type,
        size_bytes=path.stat().st_size, sha256=digest, duration_seconds=duration,
        container=container, codecs=codecs, extraction_warnings=warnings)


def prepare_video(path: Path, ffmpeg_path: str, interval: float, max_frames: int,
                  timings: dict[str, float] | None = None,
                  workload: dict | None = None) -> tuple[Path, Path | None]:
    """Extract bounded frames and a mono 16 kHz WAV into an ephemeral directory."""
    work = Path(tempfile.mkdtemp(prefix="deeptrace-media-"))
    frames = work / "frames"
    frames.mkdir()
    try:
        started = perf_counter()
        subprocess.run([ffmpeg_path, "-nostdin", "-v", "error", "-i", str(path), "-vf", f"fps=1/{interval}",
            "-frames:v", str(max_frames), "-pix_fmt", "yuvj420p", "-q:v", "2", str(frames / "frame_%06d.jpg")],
            check=True, capture_output=True, text=True, timeout=300)
        if not any(frames.glob("frame_*.jpg")):
            # Sub-interval clips can round to zero samples in the fps filter.
            subprocess.run([ffmpeg_path, "-nostdin", "-v", "error", "-i", str(path),
                "-frames:v", "1", "-pix_fmt", "yuvj420p", "-q:v", "2", str(frames / "frame_000001.jpg")],
                check=True, capture_output=True, text=True, timeout=300)
        if timings is not None:
            timings["frame extraction"] = perf_counter() - started
        if workload is not None:
            workload["frames_sampled"] = sum(1 for _ in frames.glob("frame_*.jpg"))
        audio = work / "audio.wav"
        started = perf_counter()
        result = subprocess.run([ffmpeg_path, "-nostdin", "-v", "error", "-i", str(path), "-vn", "-ac", "1",
            "-ar", "16000", "-c:a", "pcm_s16le", str(audio)], capture_output=True, text=True, timeout=300)
        if timings is not None:
            timings["audio extraction"] = perf_counter() - started
        return frames, audio if result.returncode == 0 and audio.exists() else None
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        shutil.rmtree(work, ignore_errors=True)
        raise RuntimeError(f"Media preprocessing failed: {type(exc).__name__}") from exc


def cleanup_prepared(frames: Path) -> None:
    shutil.rmtree(frames.parent, ignore_errors=True)
