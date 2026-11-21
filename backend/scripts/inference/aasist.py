"""Official AASIST input windows, with optional complete-recording coverage."""
import argparse
import importlib
import json
import shutil
import subprocess
import sys
from time import perf_counter
from pathlib import Path
from common import checkpoint_id, probability, revision, run
from audio_windows import windows, WINDOW_SAMPLES, SAMPLE_RATE


def load_audio(path, librosa, np):
    try:
        audio, _ = librosa.load(str(path), sr=16000, mono=True)
        return audio, "librosa/libsndfile"
    except Exception as primary_error:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError(
                f"libsndfile could not decode the audio and ffmpeg is unavailable: {primary_error}"
            ) from primary_error
        decoded = subprocess.run(
            [
                ffmpeg,
                "-nostdin",
                "-v",
                "error",
                "-i",
                str(path),
                "-f",
                "f32le",
                "-acodec",
                "pcm_f32le",
                "-ac",
                "1",
                "-ar",
                "16000",
                "pipe:1",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if decoded.returncode:
            detail = decoded.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                f"libsndfile failed ({primary_error}); ffmpeg failed: {detail}"
            ) from primary_error
        return np.frombuffer(decoded.stdout, dtype="<f4").copy(), "ffmpeg"


def main():
    profile = {}
    workload = {}
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('repo', 'weights', 'audio'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--variant', choices=['aasist', 'aasist-l'], default='aasist')
    parser.add_argument('--device', choices=['cpu', 'cuda'], default='cpu')
    parser.add_argument('--explain', action='store_true')
    parser.add_argument('--ig-steps', type=int, default=8)
    parser.add_argument('--window-mode', choices=['first', 'full'], default='first')
    args = parser.parse_args()
    repo = args.repo.resolve()
    name = 'AASIST-L' if args.variant == 'aasist-l' else 'AASIST'
    config_path = repo / 'config' / (name + '.conf')
    config = json.loads(config_path.read_text())['model_config']
    sys.path.insert(0, str(repo))
    started = perf_counter()
    import librosa
    import numpy as np
    import torch
    from data_utils import pad
    profile['dependency imports'] = perf_counter() - started
    workload.update({'torch_num_threads': torch.get_num_threads(),
        'torch_num_interop_threads': torch.get_num_interop_threads(), 'batch_size': 1})
    started = perf_counter()
    model = importlib.import_module('models.' + config['architecture']).Model(config).to(args.device)
    state = torch.load(str(args.weights), map_location='cpu', weights_only=True)
    state = state.get('state_dict', state)
    model.load_state_dict({k.removeprefix('module.'): v for k, v in state.items()}, strict=True)
    model.eval()
    profile['model loading'] = perf_counter() - started
    started = perf_counter()
    audio, decoder = load_audio(args.audio, librosa, np)
    if not audio.size or not np.isfinite(audio).all():
        raise ValueError('Empty or nonfinite audio')
    duration = len(audio) / 16000
    profile['AASIST decode + preprocessing'] = perf_counter() - started
    workload.update({'audio_duration_seconds': round(duration, 6), 'samples_decoded': len(audio)})
    attribution = None
    started = perf_counter()
    samples = []
    spans = list(windows(len(audio), args.window_mode))
    for index, (start, end) in enumerate(spans):
        tensor = torch.from_numpy(pad(audio[start:end], WINDOW_SAMPLES).astype(np.float32)).unsqueeze(0).to(args.device)
        with torch.inference_mode():
            _, logits = model(tensor)
            if tuple(logits.shape) != (1, 2):
                raise ValueError('Expected two ASVspoof logits')
            window_score = probability(torch.softmax(logits, dim=1)[0, 0].item())
        samples.append({'start_time': start / SAMPLE_RATE, 'end_time': end / SAMPLE_RATE,
            'fake_probability': window_score, 'logits': logits[0].detach().cpu().tolist()})
        if args.explain and index == 0:
            from audio_explain import explain_waveform
            attribution = explain_waveform(model, tensor, np, original_samples=end-start, ig_steps=args.ig_steps)
    # Within one detector only. This is a new, explicitly versioned full-window policy.
    score = sum(item['fake_probability'] for item in samples) / len(samples)
    analyzed_seconds = spans[-1][1] / SAMPLE_RATE
    workload.update({'samples_analyzed': spans[-1][1], 'inference_windows': len(samples),
        'model_input_samples': len(samples) * WINDOW_SAMPLES})
    profile['AASIST inference' if not args.explain else 'AASIST inference + attribution'] = perf_counter() - started
    started = perf_counter()
    model_version, checkpoint = name + '@' + revision(repo), checkpoint_id(args.weights)
    config_id = checkpoint_id(config_path)
    profile['provenance hashing'] = perf_counter() - started
    payload = {'model_version': model_version, 'checkpoint': checkpoint,
        'fake_probability': score, 'samples': samples,
        'coverage': {'mode': args.window_mode, 'analyzed_seconds': analyzed_seconds,
            'duration_seconds': duration, 'windows': len(samples), 'complete': args.window_mode == 'full' or len(audio) <= WINDOW_SAMPLES},
        'aggregation_method': 'mean_nonoverlapping_window_score_v1' if args.window_mode == 'full' else 'first_window_score',
        'profile': profile, 'workload': workload, 'notes': [
            f'Mono 16 kHz; {args.window_mode} window policy; {len(samples)} non-overlapping input windows of at most 64600 samples. Final short window repeat-padded; timestamps exclude padding.',
            'Audio decoder: ' + decoder + '.',
            f'Spoof class 0 softmax; uncalibrated. Analyzed {analyzed_seconds:.4f} of {duration:.4f} seconds.',
            'Full-window mean and any-window review flags are not validated operating policies.' if args.window_mode == 'full' else 'No claim about the remainder of the recording.',
            'Configuration: ' + config_id]}
    if attribution:
        payload['logits'] = attribution['logits']
        payload['attribution'] = attribution
        payload['notes'].append(
            'Attribution covers the first input window only. Temporal occlusion uses 500 ms windows. The displayed fill is local_mean. '
            'Zeros and low-level noise are stored beside it. Integrated gradients are a secondary experiment. '
            'Graph attention is internal model attention, not a timeline.'
        )
        if attribution['repeat_padded']:
            payload['notes'].append('Samples past the original recording are repeated copies of the start.')
        if attribution['truncated']:
            payload['notes'].append('Samples at or after 4.0375 seconds were outside the model input.')
    return payload


if __name__ == '__main__':
    run(main)
