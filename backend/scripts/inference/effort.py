"""Effort FaceForensics++ inference using official architecture and face alignment."""
import argparse
import os
import sys
from pathlib import Path

from common import checkpoint_id, probability, revision, run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--weights', type=Path, required=True)
    parser.add_argument('--clip', type=Path, required=True, help='Local CLIP-L/14 Hugging Face directory')
    parser.add_argument('--landmarks', type=Path, required=True)
    parser.add_argument('--frames', type=Path, required=True)
    parser.add_argument('--device', choices=['cpu', 'cuda'], default='cpu')
    args = parser.parse_args()
    repo, weights, clip, landmarks, frames = [p.resolve() for p in
        (args.repo, args.weights, args.clip, args.landmarks, args.frames)]
    for path in (weights, landmarks):
        if not path.is_file():
            raise FileNotFoundError(path)
    if not clip.is_dir() or not frames.is_dir():
        raise ValueError('CLIP and frames must be existing directories')
    model_version = revision(repo)
    training = repo / 'DeepfakeBench' / 'training'
    sys.path.insert(0, str(training))
    os.chdir(training.parent)
    import cv2
    import dlib
    import torch
    from transformers import CLIPModel
    from detectors.effort_detector import EffortDetector, apply_svd_residual_to_self_attn
    from demo import extract_aligned_face_dlib, preprocess_face

    class LocalEffort(EffortDetector):
        def build_backbone(self, config):
            backbone = CLIPModel.from_pretrained(str(clip), local_files_only=True).vision_model
            return apply_svd_residual_to_self_attn(backbone, r=1023)

    model = LocalEffort().to(args.device)
    state = torch.load(str(weights), map_location='cpu', weights_only=True)
    state = state.get('state_dict', state)
    state = {k.removeprefix('module.'): v for k, v in state.items()}
    # Never silently run with a partially loaded classifier/backbone.
    model.load_state_dict(state, strict=True)
    model.eval()
    detector = dlib.get_frontal_face_detector()
    predictor = dlib.shape_predictor(str(landmarks))
    samples, skipped = [], 0
    paths = sorted(frames.glob('frame_*.jpg'))
    if not paths:
        raise ValueError('No sampled frames found')
    with torch.inference_mode():
        for path in paths:
            image = cv2.imread(str(path))
            if image is None:
                raise ValueError(f'Unreadable frame: {path.name}')
            try:
                aligned = extract_aligned_face_dlib(detector, predictor, image, res=224)
            except IndexError:
                # Upstream assumes a second detection succeeds after alignment.
                skipped += 1
                continue
            if aligned[0] is None:
                skipped += 1
                continue
            tensor = preprocess_face(aligned[0]).to(args.device)
            result = model({'image': tensor}, inference=True)
            samples.append({'path': path.name,
                'fake_probability': probability(result['prob'].item())})
    return {'model_version': model_version, 'checkpoint': checkpoint_id(weights),
        'samples': samples, 'notes': [f'Skipped {skipped} of {len(paths)} frames without an alignable face.',
        'Only the largest detected face in each sampled frame is analyzed.',
        'Softmax scores are uncalibrated.']}


if __name__ == '__main__':
    run(main)
