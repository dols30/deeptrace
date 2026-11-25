"""Community Forensics whole-frame AI-generated-content inference (ViT-S/16 @ 384).

Scores whole frames, not face crops, so generated scenes with or without people are covered.
Default weights: Thermostatic/community-forensics-frontier-detector-2026-08, a fine-tune of
OwensLab/commfor-model-384 on recent generators with JPEG/WebP laundering augmentation.
"""
import argparse
import json
import math
from time import perf_counter
from pathlib import Path

from common import cached, checkpoint_id, file_key, probability, run

SHORT_EDGE = 440
CROP = 384
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)
PREPROCESSING_VERSION = 'rgb-bilinear-short440-round-center384-imagenet-v1'


def shifted_score(logit, boundary):
    value = logit - boundary
    return 1 / (1 + math.exp(-value)) if value >= 0 else math.exp(value) / (1 + math.exp(value))


def image_tensor(path):
    """Shared by inference and the opt-in head-adaptation experiment; unchanged pixel path."""
    import numpy as np
    import torch
    from PIL import Image
    with Image.open(path) as image:
        image = image.convert('RGB')
        scale = SHORT_EDGE / min(image.size)
        image = image.resize((max(CROP, round(image.width * scale)), max(CROP, round(image.height * scale))),
            Image.Resampling.BILINEAR)
        left, top = (image.width - CROP) // 2, (image.height - CROP) // 2
        image = image.crop((left, top, left + CROP, top + CROP))
        tensor = torch.from_numpy(np.asarray(image).copy()).permute(2, 0, 1).float().div(255)
    mean = torch.tensor(IMAGENET_MEAN).view(3, 1, 1)
    std = torch.tensor(IMAGENET_STD).view(3, 1, 1)
    return (tensor - mean) / std


def apply_adaptation(model, config_path, base_weights):
    """Research head only, explicitly requested by CLI and bound to its base checkpoint."""
    import hashlib
    from safetensors.torch import load_file
    config = json.loads(config_path.read_text())
    head = config_path.parent / 'head.safetensors'
    def digest(path):
        with path.open('rb') as stream:
            return hashlib.file_digest(stream, 'sha256').hexdigest()
    boundary = config.get('raw_logit_boundary')
    if (config.get('schema') != 'commfor_head_adaptation_v1'
            or config.get('preprocessing_version') != PREPROCESSING_VERSION
            or config.get('base_sha256') != digest(base_weights)
            or config.get('head_sha256') != digest(head)
            or type(boundary) not in (int, float) or not math.isfinite(boundary)
            or not config.get('development_protocol_sha256')):
        raise ValueError('Invalid or incompatible research adaptation')
    model.head.load_state_dict(load_file(str(head)), strict=True)
    return config, checkpoint_id(head)


def main(argv=None):
    profile = {}
    workload = {}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--weights', type=Path, required=True, help='timm vit_small_patch16_384 safetensors')
    parser.add_argument('--config', type=Path, help='release config.json (supplies raw_logit_boundary)')
    parser.add_argument('--boundary', type=float, help='raw-logit decision boundary; overrides --config')
    parser.add_argument('--revision', default='unpinned', help='model repository revision to report')
    parser.add_argument('--adaptation', type=Path, help='Opt-in research head config; never enabled by default')
    parser.add_argument('--frames', type=Path, required=True)
    parser.add_argument('--device', choices=['cpu', 'cuda', 'mps'], default='cpu')
    args = parser.parse_args(argv)
    weights, frames = args.weights.resolve(), args.frames.resolve()
    if not weights.is_file():
        raise FileNotFoundError(weights)
    if not frames.is_dir():
        raise ValueError('frames must be an existing directory')
    paths = sorted(frames.glob('frame_*.jpg'))
    if not paths:
        raise ValueError('No sampled frames found')
    boundary = args.boundary
    if boundary is None:
        if not args.config:
            raise ValueError('Provide --config or --boundary; an uncalibrated boundary is not assumed')
        boundary = float(json.loads(args.config.read_text())['raw_logit_boundary'])

    started = perf_counter()
    import timm
    import torch
    from safetensors.torch import load_file
    profile['dependency imports'] = perf_counter() - started
    workload.update({'torch_num_threads': torch.get_num_threads(),
        'torch_num_interop_threads': torch.get_num_interop_threads(), 'batch_size': 1})

    started = perf_counter()
    if args.adaptation and args.boundary is not None:
        raise ValueError('An adapted head must use its frozen development boundary')

    def load():
        model = timm.create_model('vit_small_patch16_384', pretrained=False, num_classes=1)
        state = {k.removeprefix('vit.'): v for k, v in load_file(str(weights)).items()}
        model.load_state_dict(state, strict=True)
        adaptation, head_checkpoint = None, None
        if args.adaptation:
            adaptation, head_checkpoint = apply_adaptation(model, args.adaptation.resolve(), weights)
        model.to(args.device).eval()
        return model, adaptation, head_checkpoint

    adaptation_files = (args.adaptation, args.adaptation.parent / 'head.safetensors') if args.adaptation else ()
    model, adaptation, head_checkpoint = cached(
        ('commfor', args.device, file_key(weights, *adaptation_files)), load)
    if adaptation:
        boundary = adaptation['raw_logit_boundary']
    profile['model loading'] = perf_counter() - started

    samples = []
    preprocessing_seconds = 0.0
    inference_seconds = 0.0
    with torch.inference_mode():
        for path in paths:
            started = perf_counter()
            tensor = image_tensor(path)
            preprocessing_seconds += perf_counter() - started
            started = perf_counter()
            logit = model(tensor[None].to(args.device)).float().item()
            inference_seconds += perf_counter() - started
            if not math.isfinite(logit):
                raise ValueError(f'Non-finite logit for {path.name}')
            samples.append({'path': path.name, 'fake_probability': probability(shifted_score(logit, boundary)),
                'logits': [logit]})
    profile.update({'CommFor preprocessing': preprocessing_seconds, 'CommFor inference': inference_seconds})
    workload.update({'frames_received': len(paths), 'frames_analyzed': len(samples)})
    started = perf_counter()
    checkpoint = checkpoint_id(weights)
    profile['provenance hashing'] = perf_counter() - started
    notes = [] if adaptation is None else [
        'Opt-in research head: ' + head_checkpoint,
        'Development protocol: ' + adaptation['development_protocol_sha256'],
        'Adapted head and decision boundary selected on development data; not DPS validated.']
    return {'model_version': args.revision + ('+head-adaptation-v1' if adaptation else ''), 'checkpoint': checkpoint, 'samples': samples,
        'profile': profile, 'workload': workload,
        'notes': [*notes, f'Scored {len(samples)} of {len(paths)} frames as whole images (no face alignment).',
            f'Short edge resized to {SHORT_EDGE}px, centre {CROP}px crop; frame edges outside the crop are not seen.',
            f'Scores are sigmoid(logit - {boundary:g}): 0.5 is the release decision boundary, not a calibrated probability.',
            'Trained on still images; temporal artefacts and video-codec effects are not modelled.']}


if __name__ == '__main__':
    run(main)
