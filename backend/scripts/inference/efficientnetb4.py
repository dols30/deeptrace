"""DeepfakeBench EfficientNet-B4 with upstream face alignment and strict FF++ weights."""
import argparse
import importlib.util
from time import perf_counter
from pathlib import Path
from common import add_sys_path, cached, checkpoint_id, file_key, probability, revision, run
from face_coverage import FaceCoverageTracker


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv=None):
    profile = {}
    workload = {}
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('repo', 'weights', 'landmarks', 'frames'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--device', choices=['cpu', 'cuda'], default='cpu')
    parser.add_argument('--explain', action='store_true',
        help='Compute Grad-CAM and the face-alignment matrix for each scored crop.')
    parser.add_argument('--explain-dir', type=Path,
        help='When --explain is set, write the crop, the crop overlay, and the frame overlay here.')
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    add_sys_path(repo / 'training')
    started = perf_counter()
    import cv2
    import dlib
    import numpy as np
    import torch
    profile['dependency imports'] = perf_counter() - started
    workload.update({'torch_num_threads': torch.get_num_threads(),
        'torch_num_interop_threads': torch.get_num_interop_threads(), 'batch_size': 1})
    started = perf_counter()

    def load():
        network = load_module('deeptrace_effnet', repo / 'training/networks/efficientnetb4.py')
        preprocessing = load_module('deeptrace_face', repo / 'preprocessing/preprocess.py')
        model = network.EfficientNetB4(dict(num_classes=2, inc=3, dropout=False, mode='Original', pretrained=False))
        state = torch.load(str(args.weights), map_location='cpu', weights_only=True)
        state = state.get('state_dict', state)
        state = {k.removeprefix('module.'): v for k, v in state.items()}
        # Official detector checkpoints contain only the backbone's learned parameters.
        state = {k.removeprefix('backbone.'): v for k, v in state.items()}
        model.load_state_dict(state, strict=True)
        model.to(args.device).eval()
        return preprocessing, model, dlib.get_frontal_face_detector(), dlib.shape_predictor(str(args.landmarks))

    preprocessing, model, face_detector, predictor = cached(
        ('efficientnetb4', str(repo), args.device, file_key(args.weights, args.landmarks)), load)
    # The tracker holds per-request coverage counts, so it is never cached.
    detector = FaceCoverageTracker(face_detector)
    profile['model + face detector loading'] = perf_counter() - started
    paths = sorted(args.frames.glob('frame_*.jpg'))
    if not paths:
        raise ValueError('No sampled frames found')
    samples = []
    checked = False
    decode_seconds = 0.0
    alignment_seconds = 0.0
    tensor_seconds = 0.0
    inference_seconds = 0.0
    for path in paths:
        started = perf_counter()
        image = cv2.imread(str(path))
        decode_seconds += perf_counter() - started
        if image is None:
            raise ValueError('Unreadable frame: ' + path.name)
        detector.begin_frame()
        if args.explain:
            from face_geometry import align_face
            from gradcam import attribution_record
            started = perf_counter()
            aligned = align_face(preprocessing, detector, predictor, image, res=256)
            detector.finish_frame(aligned is not None)
            alignment_seconds += perf_counter() - started
            if aligned is None:
                continue
            started = perf_counter()
            rgb = cv2.cvtColor(aligned['crop'], cv2.COLOR_BGR2RGB).astype(np.float32) / 255
            tensor = torch.from_numpy(((rgb - 0.5) / 0.5).transpose(2, 0, 1).copy()).unsqueeze(0).to(args.device)
            tensor_seconds += perf_counter() - started
            started = perf_counter()
            record, _logits, score = attribution_record(
                model, tensor, aligned, image, args.explain_dir, path.stem, sanity=not checked)
            inference_seconds += perf_counter() - started
            checked = True
            samples.append({'path': path.name, 'fake_probability': probability(score),
                'logits': record['logits'], 'attribution': record})
            continue
        started = perf_counter()
        face, _, _ = preprocessing.extract_aligned_face_dlib(detector, predictor, image, res=256)
        detector.finish_frame(face is not None)
        alignment_seconds += perf_counter() - started
        if face is None:
            continue
        started = perf_counter()
        rgb = cv2.cvtColor(face, cv2.COLOR_BGR2RGB).astype(np.float32) / 255
        tensor = torch.from_numpy(((rgb - 0.5) / 0.5).transpose(2, 0, 1).copy()).unsqueeze(0).to(args.device)
        tensor_seconds += perf_counter() - started
        started = perf_counter()
        with torch.inference_mode():
            logits = model(tensor)
        inference_seconds += perf_counter() - started
        if tuple(logits.shape) != (1, 2):
            raise ValueError('Expected two FF++ logits')
        samples.append({'path': path.name, 'fake_probability': probability(torch.softmax(logits, dim=1)[0, 1].item())})
    notes = [
        f'Scored {len(samples)} of {len(paths)} sampled frames; unalignable faces skipped.',
        'Largest face only; upstream 256px alignment, RGB normalization mean/std 0.5; fake class 1.',
        'Landmarks: ' + checkpoint_id(args.landmarks),
    ]
    if args.explain:
        notes.append('Grad-CAM on EfficientNetB4.features for fake logit 1. Heatmap is model sensitivity, not a manipulation map.')
    else:
        notes.append('Uncalibrated frame scores. Pass --explain to attach Grad-CAM and the face-alignment matrix.')
    profile.update({'JPEG decode': decode_seconds, 'face detection/alignment': alignment_seconds,
        'EfficientNet preprocessing': tensor_seconds, 'EfficientNet inference': inference_seconds})
    workload.update({'frames_received': len(paths), 'faces_analyzed': len(samples),
        'frames_analyzed': len(samples)})
    started = perf_counter()
    model_version, checkpoint = 'efficientnetb4@' + revision(repo), checkpoint_id(args.weights)
    profile['provenance hashing'] = perf_counter() - started
    return {'model_version': model_version, 'checkpoint': checkpoint,
        'samples': samples, 'notes': notes, 'profile': profile, 'workload': workload,
        'coverage': detector.summary()}


if __name__ == '__main__':
    run(main)
