"""Official ASVspoof 2021 DF LFCC-LCNN; full-recording window policy."""
import argparse
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from common import add_sys_path, cached, checkpoint_id, file_key, probability, revision, run
from aasist import load_audio
from audio_windows import windows, WINDOW_SAMPLES, SAMPLE_RATE


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('repo', 'weights', 'audio'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--device', choices=['cpu', 'cuda'], default='cpu')
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    add_sys_path(repo / 'LA/Baseline-LFCC-LCNN')
    import numpy as np
    import librosa
    import torch
    from lfcc_compat import install
    install(torch)

    def load():
        spec = importlib.util.spec_from_file_location('deeptrace_lfcc_model',
            repo / 'DF/Baseline-LFCC-LCNN/project/baseline_DF/model.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        # The protocol file provides training labels only; inference never reads labels.
        config = SimpleNamespace(optional_argument=[str(repo / 'deeptrace-inference-no-labels')])
        model = module.Model(1, 1, SimpleNamespace(), config)
        model.load_state_dict(torch.load(args.weights, map_location='cpu', weights_only=True), strict=True)
        model.to(args.device).eval()
        return model

    model = cached(('lfcc_lcnn', str(repo), args.device, file_key(args.weights)), load)
    audio, decoder = load_audio(args.audio, librosa, np)
    if not audio.size or not np.isfinite(audio).all():
        raise ValueError('Empty or nonfinite audio')
    samples = []
    for start, end in windows(len(audio), 'full'):
        segment = audio[start:end]
        padded = np.tile(segment, (WINDOW_SAMPLES + len(segment) - 1) // len(segment))[:WINDOW_SAMPLES]
        tensor = torch.from_numpy(padded.astype(np.float32)).reshape(1, -1, 1).to(args.device)
        with torch.inference_mode():
            embedding = model._compute_embedding(tensor, [WINDOW_SAMPLES])
            logit = model._compute_score(embedding, inference=True).reshape(-1)
            if logit.numel() != 1:
                raise ValueError('Expected one bona-fide logit')
            value = probability(torch.sigmoid(-logit[0]).item())
        samples.append({'start_time': start / SAMPLE_RATE, 'end_time': end / SAMPLE_RATE,
            'fake_probability': value, 'logits': logit.cpu().tolist()})
    duration = len(audio) / SAMPLE_RATE
    return {'model_version': 'LFCC-LCNN-DF@' + revision(repo), 'checkpoint': checkpoint_id(args.weights),
        'fake_probability': sum(s['fake_probability'] for s in samples) / len(samples), 'samples': samples,
        'coverage': {'mode': 'full', 'duration_seconds': duration, 'analyzed_seconds': duration,
            'windows': len(samples), 'complete': True}, 'aggregation_method': 'mean_nonoverlapping_window_score_v1',
        'notes': ['Decoder: ' + decoder + '; mono 16 kHz.',
            'Official DF frontend: 20 LFCCs plus delta/delta-delta, 320-sample frames, 160-sample hop, 1024-point FFT, maximum 4 kHz.',
            'Raw logit is oriented bona fide; displayed artifact score is sigmoid(-logit), uncalibrated. No exact vocoder attribution.',
            'Local PoC policy: non-overlapping 64600-sample windows; final short window repeat-padded. Timestamps exclude padding. Mean score and any-window 0.5 flags are unvalidated.']}


if __name__ == '__main__':
    run(main)
