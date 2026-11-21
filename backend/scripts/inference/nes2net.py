"""ASVspoof 19/21 wav2vec2 Nes2Net-X inference (not the singing-voice variant)."""
import argparse
import sys
from pathlib import Path
from types import SimpleNamespace

from common import checkpoint_id, probability, revision, run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--weights', type=Path, required=True)
    parser.add_argument('--xlsr', type=Path, required=True, help='Official xlsr2_300m.pt frontend')
    parser.add_argument('--audio', type=Path, required=True)
    parser.add_argument('--device', choices=['cpu', 'cuda'], default='cpu')
    parser.add_argument('--test-mode', choices=['4s', 'full'], default='4s')
    args = parser.parse_args()
    repo, weights, xlsr, audio_path = [p.resolve() for p in
        (args.repo, args.weights, args.xlsr, args.audio)]
    for path in (weights, xlsr, audio_path):
        if not path.is_file():
            raise FileNotFoundError(path)
    model_version = revision(repo)
    sys.path.insert(0, str(repo))
    import librosa
    import numpy as np
    import torch
    import fairseq
    from model_scripts import wav2vec2_Nes2Net_X as upstream

    class LocalSSL(upstream.SSLModel):
        def __init__(self, device):
            torch.nn.Module.__init__(self)
            models, _, _ = fairseq.checkpoint_utils.load_model_ensemble_and_task([str(xlsr)])
            self.model, self.device, self.out_dim = models[0], device, 1024

    # Replace only the hard-coded frontend path, preserving upstream feature extraction.
    upstream.SSLModel = LocalSSL
    config = SimpleNamespace(n_output_logits=2, dilation=2, pool_func='mean',
        SE_ratio=[1], Nes_ratio=[8, 8])
    model = upstream.wav2vec2_Nes2Net_no_Res_w_allT(config, args.device).to(args.device)
    state = torch.load(str(weights), map_location='cpu', weights_only=True)
    state = state.get('state_dict', state)
    model.load_state_dict({k.removeprefix('module.'): v for k, v in state.items()}, strict=True)
    model.eval()
    audio, _ = librosa.load(str(audio_path), sr=16000, mono=True)
    if audio.size == 0 or not np.isfinite(audio).all():
        raise ValueError('Empty or nonfinite audio')
    original_duration = len(audio) / 16000
    if args.test_mode == '4s':
        audio = np.tile(audio, int(64000 / len(audio)) + 1)[:64000]
    with torch.inference_mode():
        logits = model(torch.from_numpy(audio).unsqueeze(0).to(args.device))
        if tuple(logits.shape) != (1, 2):
            raise ValueError('Expected two ASVspoof class logits')
        # Official data_utils.py: spoof=0, bonafide=1. Demo prints a real-class logit.
        score = probability(torch.softmax(logits, dim=1)[0, 0].item())
    return {'model_version': model_version, 'checkpoint': checkpoint_id(weights),
        'fake_probability': score, 'notes': [
        'ASVspoof Nes2Net-X with XLS-R frontend; spoof class is index 0.',
        f'Input duration: {original_duration:.3f}s; evaluation mode: {args.test_mode}.',
        '4s mode evaluates only the first four seconds and repeats shorter clips.' if args.test_mode == '4s'
        else 'Full-length evaluation; memory usage grows with recording duration.',
        'Softmax score is uncalibrated; this is not the upstream raw bona-fide logit.']}


if __name__ == '__main__':
    run(main)
