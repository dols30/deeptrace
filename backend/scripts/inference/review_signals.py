"""Descriptive PoC measurements on original decoded media; no authenticity classifier."""
import argparse
from pathlib import Path

from common import checkpoint_id, run
from review_math import block_boundary_ratio, closure_intervals, eye_aspect_ratio, spectrum_metrics

VERSION = "review-signals-v1"
METHODS = {
    "gan_frequency": ("Generated-image frequency review", "video"),
    "blink": ("Eye closure and blinking", "video"),
    "facial_motion": ("Facial movement", "video"),
    "compression": ("Compression patterns", "video"),
    "mel_spectrogram": ("Mel-spectrogram analysis", "audio"),
    "vocoder": ("Spectral artifact review", "audio"),
    "background_noise": ("Background-noise consistency", "audio"),
}


def check(key, status, method, summary, measurements=None, intervals=None, limitations=None):
    title, modality = METHODS[key]
    return {"technique": key, "title": title, "modality": modality, "status": status,
        "method": method, "summary": summary, "measurements": measurements or {},
        "intervals": intervals or [], "version": VERSION, "validated": False,
        "limitations": ["Descriptive measurements are not a validated manipulation test.", *(limitations or [])]}


def audio_checks(path, maximum, np):
    import librosa
    from aasist import load_audio
    audio, decoder = load_audio(path, librosa, np)
    if not audio.size or not np.isfinite(audio).all():
        raise ValueError("Empty/nonfinite audio")
    duration = len(audio) / 16000
    audio = audio[:int(maximum * 16000)]
    analyzed = len(audio) / 16000
    if len(audio) < 512:
        raise ValueError("At least 32 ms of audio is needed for spectral measurements")
    power = np.abs(librosa.stft(audio, n_fft=512, hop_length=160, center=False)) ** 2
    mel = librosa.feature.melspectrogram(S=power, sr=16000, n_fft=512, n_mels=64)
    mel_db = librosa.power_to_db(mel, ref=1.0)
    energy = librosa.feature.rms(S=np.sqrt(power), frame_length=512)[0]
    common = {"analyzed_seconds": round(analyzed, 4), "recording_seconds": round(duration, 4),
        "sample_rate_hz": 16000, "hop_ms": 10, "fft_samples": 512}
    coverage_limit = f"Analyzed the opening {analyzed:.2f}s of {duration:.2f}s; decoder {decoder}."
    mel_result = check("mel_spectrogram", "measured", "64-band mel power spectrogram, 32 ms Hann windows / 10 ms hop",
        "Mel-band energy was measured across the analyzed audio.",
        {**common, "mel_bands": 64, "frames": int(mel.shape[1]),
            "mean_band_power_db": ", ".join(f"{v:.2f}" for v in mel_db.mean(axis=1))},
        limitations=[coverage_limit, "Absolute energy depends on recording gain. No learned mel-based classifier is fitted."])
    flatness = librosa.feature.spectral_flatness(S=np.sqrt(power))[0]
    centroid = librosa.feature.spectral_centroid(S=np.sqrt(power), sr=16000)[0]
    intervals = []
    for start in range(0, power.shape[1], 100):
        stop = min(start + 100, power.shape[1])
        intervals.append({"start_time": start * .01, "end_time": min(analyzed, stop * .01 + .022),
            "flatness": round(float(flatness[start:stop].mean()), 6),
            "centroid_hz": round(float(centroid[start:stop].mean()), 2)})
    spectral = check("vocoder", "measured", "Short-time spectral flatness and centroid",
        "Spectral features are available for artifact review; no vocoder was identified.",
        {**common, "mean_flatness": float(flatness.mean()), "mean_centroid_hz": float(centroid.mean())},
        intervals[:120], [coverage_limit, "A microphone, codec, denoiser, music, or speech can produce the same features.",
            "Specific vocoder identification requires a separately trained and validated classifier."])
    # Low-energy frames are candidates for noise review, not a claim of speech-free segmentation.
    quiet = []
    for start in range(0, len(energy), 100):
        block = energy[start:start+100]
        cutoff = float(np.quantile(block, .2))
        selected = block[block <= cutoff]
        if len(selected) >= 20:
            quiet.append({"start_time": start * .01, "end_time": min(analyzed, (start+len(block))*.01+.022),
                "low_energy_rms_dbfs": round(float(20*np.log10(max(float(selected.mean()), 1e-12))), 2)})
    changes = []
    for previous, current in zip(quiet, quiet[1:]):
        delta = current["low_energy_rms_dbfs"] - previous["low_energy_rms_dbfs"]
        if abs(delta) >= 12:
            changes.append({**current, "change_db": round(delta, 2),
                "description": "Low-energy level change; review recording gain, environment, and edits"})
    noise = check("background_noise", "measured" if len(quiet) >= 2 else "unavailable",
        "Within-block bottom-20% RMS frames; at least 20 low-energy candidates per 1s block; 12 dB review-change rule",
        f"{len(changes)} low-energy level changes need listening review." if changes else
        "Low-energy candidates were measured; no large level change was returned." if len(quiet) >= 2 else
        "Insufficient low-energy blocks for a background-noise comparison.",
        {**common, "low_energy_blocks": len(quiet), "level_changes": len(changes), "review_change_db": 12},
        changes[:120], [coverage_limit, "Low energy does not establish absence of speech. No isolated background-noise track is available.",
            "Changes can reflect automatic gain, a new environment, or normal recording conditions; the 12 dB rule is exploratory."])
    return [mel_result, spectral, noise]


def video_checks(path, maximum, landmarks, np):
    import cv2
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError("Cannot decode video")
    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        if not np.isfinite(fps) or fps <= 0:
            raise ValueError("No usable video frame rate")
        count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        detector = predictor = None
        if landmarks and landmarks.is_file():
            import dlib
            detector, predictor = dlib.get_frontal_face_detector(), dlib.shape_predictor(str(landmarks))
        ears, movements, boundaries, frequencies = [], [], [], []
        previous_shape = previous_box = previous_time = None
        step = max(1, int(round(fps / 30)))
        landmark_frames = attempted = decoded = 0
        # Native pixels for frequency/block review. Resizing would change the compression grid.
        for index in range(min(count if count > 0 else int(maximum * fps), int(maximum * fps))):
            ok, frame = cap.read()
            if not ok:
                break
            decoded += 1
            timestamp = index / fps
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if index % max(1, round(fps)) == 0:
                boundaries.append(block_boundary_ratio(gray, np))
                frequencies.append(spectrum_metrics(gray, np)["high_frequency_energy_ratio"])
            if detector is None or index % step:
                continue
            attempted += 1
            scale = min(1.0, 640 / gray.shape[1])
            small = cv2.resize(gray, None, fx=scale, fy=scale) if scale < 1 else gray
            faces = detector(small, 0)
            if not faces:
                previous_shape = previous_box = previous_time = None
                continue
            face = max(faces, key=lambda item: item.width() * item.height())
            box = np.array([face.left(), face.top(), face.right(), face.bottom()], dtype=float)
            shape = predictor(small, face)
            points = np.array([[shape.part(i).x, shape.part(i).y] for i in range(68)], dtype=float)
            left, right = eye_aspect_ratio(points[36:42]), eye_aspect_ratio(points[42:48])
            if left is None or right is None:
                continue
            landmark_frames += 1
            # Track continuity is conservative: exclude cuts, large pose shifts and identity switches.
            continuous = False
            if previous_box is not None:
                overlap = np.maximum(0, np.minimum(box[2:], previous_box[2:]) - np.maximum(box[:2], previous_box[:2]))
                intersection = float(overlap.prod())
                union = float((box[2:]-box[:2]).prod() + (previous_box[2:]-previous_box[:2]).prod() - intersection)
                continuous = intersection / max(union, 1) >= .5 and timestamp - previous_time <= step/fps * 1.5
            if not continuous and ears:
                ears.append((timestamp, None))  # Explicit gap; never connect closures across a cut.
            ears.append((timestamp, (left+right)/2))
            eye_distance = float(np.linalg.norm(points[36]-points[45]))
            normalized = (points-points[30]) / max(eye_distance, 1)
            if continuous:
                movements.append(float(np.linalg.norm(normalized[17:]-previous_shape[17:], axis=1).mean()))
            previous_shape, previous_box, previous_time = normalized, box, timestamp
        if not decoded:
            raise ValueError("No decoded frames")
        coverage = {"analyzed_seconds": round(decoded/fps, 4), "recording_seconds": round(count/fps, 4),
            "source_fps": fps, "landmark_sample_fps": fps/step, "decoded_frames": decoded,
            "face_frames": landmark_frames, "landmark_frames_attempted": attempted}
        limit = f"Opening {decoded/fps:.2f}s only; largest face; landmarks sampled at {fps/step:.2f} fps."
        frequency = check("gan_frequency", "measured", "Native-pixel, Hann-windowed 2D FFT; energy above normalized radius 0.5",
            "Spatial frequency statistics were measured; no GAN architecture or artifact was identified.",
            {**coverage, "frames_measured": len(frequencies), "mean_high_frequency_energy_ratio": float(np.mean(frequencies))},
            limitations=[limit, "Scene texture, rescaling, camera processing and codecs confound frequency patterns.",
                "Use the generated-image model result separately; these statistics are not a GAN classifier."])
        compression = check("compression", "measured", "8-pixel boundary/interior absolute-luma-difference ratio on native decoded frames",
            "Block-grid contrast was measured without re-encoding the input.",
            {**coverage, "frames_measured": len(boundaries), "mean_grid_ratio": float(np.mean(boundaries)), "max_grid_ratio": max(boundaries)},
            limitations=[limit, "Not a compression-history reconstruction or tamper localization method.",
                "Camera codec, natural edges, frame-grid alignment and earlier rescaling affect this statistic."])
        valid_ears = [value for _, value in ears if value is not None]
        baseline = float(np.median(valid_ears)) if valid_ears else 0
        candidates = closure_intervals(ears, baseline * .7, step/fps*1.5) if baseline else []
        usable = landmark_frames >= 10 and fps/step >= 15
        blink = check("blink", "measured" if usable else "unavailable", "Six-point eye aspect ratio; closure candidates below 70% of recording median",
            f"{len(candidates)} candidate eye closures were returned for review." if usable else "Insufficient reliable face samples or frame rate for blinking review.",
            {**coverage, "median_eye_aspect_ratio": baseline, "relative_closure_threshold": baseline*.7, "closure_candidates": len(candidates)},
            candidates[:120] if usable else [], [limit, "No validated unnatural-blinking classifier. Pose, glasses, occlusion and tracking errors affect landmarks.",
                "Candidate closures are not confirmed blinks; the relative threshold is exploratory.",
                "Landmarks: " + checkpoint_id(landmarks) if detector else "No reviewed landmark predictor configured."])
        motion = check("facial_motion", "measured" if movements else "unavailable",
            "Nose-centered, inter-eye-normalized landmark displacement within continuous face tracks",
            "Facial movement was measured; micro-expressions were not classified." if movements else "Insufficient continuous face tracking for facial movement review.",
            {**coverage, "mean_landmark_displacement": float(np.mean(movements)) if movements else 0,
                "max_landmark_displacement": max(movements) if movements else 0},
            limitations=[limit, "Head rotation, expression, cuts and tracking jitter can cause movement.",
                "Sparse/ordinary-rate footage and this landmark statistic cannot establish micro-expression anomalies."])
        return [frequency, blink, motion, compression]
    finally:
        cap.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--media', type=Path, required=True)
    parser.add_argument('--landmarks', type=Path)
    parser.add_argument('--max-seconds', type=float, default=30)
    args = parser.parse_args()
    if not 0 < args.max_seconds <= 120:
        raise ValueError('max-seconds must be in (0,120]')
    import numpy as np
    checks = []
    video = args.media.suffix.lower() in {'.mp4', '.mov', '.avi', '.mkv', '.webm'}
    if video:
        try:
            checks.extend(video_checks(args.media, args.max_seconds, args.landmarks, np))
        except Exception as exc:
            checks.extend(check(key, 'error', 'Not completed', 'Video measurements failed: '+type(exc).__name__)
                for key, (_, modality) in METHODS.items() if modality == 'video')
    else:
        checks.extend(check(key, 'not_applicable', 'Not run', 'Video method does not apply to audio-only input.')
            for key, (_, modality) in METHODS.items() if modality == 'video')
    try:
        checks.extend(audio_checks(args.media, args.max_seconds, np))
    except Exception as exc:
        checks.extend(check(key, 'unavailable', 'Not completed', 'No usable audio measurements: '+type(exc).__name__)
            for key, (_, modality) in METHODS.items() if modality == 'audio')
    return {'checks': checks}


if __name__ == '__main__':
    run(main)
