"""SOFTNet released CAS(ME)2 micro-expression interval spotter, not a fake classifier."""
import argparse
import ast
import importlib.util
import os
from pathlib import Path
import tempfile
from common import checkpoint_id, revision, run


def load_model(repo, weights):
    # Execute the authors' architecture, excluding training-only optimizer setup.
    # HDF5 contains numeric weights only; load_weights rejects missing/shape-mismatched layers.
    os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '2')
    from tensorflow import keras
    source = ast.parse((repo / 'training.py').read_text())
    function = next(n for n in source.body if isinstance(n, ast.FunctionDef) and n.name == 'SOFTNet')
    stop = next(i for i, n in enumerate(function.body) if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == 'model' for t in n.targets))
    function.body = function.body[:stop+1] + [ast.Return(value=ast.Name(id='model', ctx=ast.Load()))]
    tree = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    namespace = {'keras': keras, 'layers': keras.layers}
    exec(compile(tree, str(repo / 'training.py'), 'exec'), namespace)
    model = namespace['SOFTNet']()
    model.load_weights(str(weights), skip_mismatch=False)
    return model


def spot_intervals(scores, fps=30., k=6):
    import numpy as np
    from scipy.signal import find_peaks
    values = np.asarray(scores, dtype=float).reshape(-1)
    if len(values) <= 2*k or not np.isfinite(values).all():
        raise ValueError('Insufficient or invalid spotting scores')
    # Match released code: a 2*k moving mean, edge trim k, p=0.55.
    smooth = np.array([values[i:i+2*k].mean() for i in range(len(values)-2*k)])
    threshold = float(smooth.mean() + .55 * (smooth.max() - smooth.mean()))
    peaks = [] if np.ptp(smooth) < 1e-7 else find_peaks(smooth, height=threshold, distance=k)[0]
    return [{'start_time': float(p/fps), 'end_time': float((p+2*k)/fps),
        'peak_time': float((p+k)/fps), 'regression_score': float(smooth[p])} for p in peaks], threshold


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('repo', 'weights', 'media', 'landmarks'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--max-seconds', type=float, default=30.)
    args = parser.parse_args()
    if not 1 <= args.max_seconds <= 120:
        raise ValueError('max-seconds must be between 1 and 120')
    repo, weights, landmarks = args.repo.resolve(), args.weights.resolve(), args.landmarks.resolve()
    import cv2
    import dlib
    import numpy as np
    base = {'technique': 'micro_expression', 'title': 'Micro-expression intervals', 'modality': 'video',
        'status': 'unavailable', 'method': 'SOFTNet CAS(ME)2 micro-expression spotting, fold s1',
        'version': 'SOFTNet@' + revision(repo), 'validated': False, 'measurements': {
            'checkpoint': checkpoint_id(weights), 'landmarks': checkpoint_id(landmarks)},
        'intervals': [], 'limitations': [
            'Expression spotting is not manipulation, emotion, deception or authenticity classification.',
            'Single released leave-one-subject-out checkpoint; no DPS validation or calibrated scores.',
            'Requires one stable visible face and at least 30 source frames/second. Opening segment only; no conclusion about unexamined material.',
            'Fixed-reference face crops can miss movement after pose, lighting or scene changes.']}
    capture = cv2.VideoCapture(str(args.media))
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    if not np.isfinite(fps) or fps < 29.:
        capture.release()
        return {**base, 'summary': 'Not scored: the source frame rate is insufficient for this 30 fps model.'}
    detector = dlib.get_frontal_face_detector()
    crops, box, times = [], None, []
    index, next_time = 0, 0.
    reason = None
    while True:
        ok, image = capture.read()
        if not ok or index/fps >= args.max_seconds:
            break
        timestamp = index/fps
        index += 1
        if timestamp + 1e-6 < next_time:
            continue
        next_time += 1/30
        if box is None or len(crops) % 15 == 0:
            faces = detector(image, 1)
            if len(faces) != 1:
                reason = 'Not scored: a single continuously visible face could not be established.'
                break
            face = faces[0]
            current = np.array([max(0, face.left()), max(0, face.top()),
                min(image.shape[1], face.right()), min(image.shape[0], face.bottom())])
            if box is not None and np.max(np.abs(current-box)) > .2 * min(box[2:]-box[:2]):
                reason = 'Not scored: face movement or a scene change exceeded the fixed-crop coverage limit.'
                break
            if box is None:
                box = current
        left, top, right, bottom = box
        crop = cv2.resize(image[top:bottom, left:right], (128, 128))
        # The authors save face crops as JPEG then read grayscale; preserve that step.
        ok, encoded = cv2.imencode('.jpg', crop)
        if not ok:
            raise ValueError('Could not encode face crop')
        crops.append(cv2.imdecode(encoded, cv2.IMREAD_GRAYSCALE))
        times.append(timestamp)
    capture.release()
    if reason or len(crops) <= 18:
        return {**base, 'summary': reason or 'Not scored: the recording is too short for the spotting window.'}
    # Fail closed before upstream's unbounded landmark search if the reference crop has no face.
    if not detector(crops[0], 1):
        return {**base, 'summary': 'Not scored: facial landmarks could not be established in the reference crop.'}
    spec = importlib.util.spec_from_file_location('deeptrace_softnet_features', repo / 'extraction_preprocess.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cwd = Path.cwd()
    try:
        with tempfile.TemporaryDirectory(prefix='softnet-') as temporary:
            # Upstream has a Windows-style literal path. Resolve it locally without modifying vendor code.
            (Path(temporary) / 'Utils\\shape_predictor_68_face_landmarks.dat').symlink_to(landmarks)
            os.chdir(temporary)
            features = np.asarray(module.extract_preprocess([np.asarray(crops)], 6)[0], dtype=np.float32)
    finally:
        os.chdir(cwd)
    for sample in features:
        for channel in range(3):
            sample[:, :, channel] = cv2.normalize(sample[:, :, channel], None, 0, 1, cv2.NORM_MINMAX)
    if not np.isfinite(features).all():
        raise ValueError('Nonfinite optical-flow features')
    model = load_model(repo, weights)
    scores = []
    for start in range(0, len(features), 32):
        batch = features[start:start+32]
        values = model([batch[:, :, :, i:i+1] for i in range(3)], training=False).numpy().reshape(-1)
        scores.extend(values.tolist())
    intervals, threshold = spot_intervals(scores)
    return {**base, 'status': 'measured',
        'summary': f'{len(intervals)} candidate brief-expression interval' + ('' if len(intervals) == 1 else 's') + ' for visual review.',
        'measurements': {**base['measurements'], 'source_fps': fps, 'analysis_fps': 30,
            'analyzed_seconds': times[-1]+1/30, 'analyzed_frames': len(crops), 'flow_lag_frames': 6,
            'candidate_intervals': len(intervals), 'adaptive_regression_threshold': threshold,
            'minimum_regression_score': min(scores), 'maximum_regression_score': max(scores)},
        'intervals': intervals}


if __name__ == '__main__':
    run(main)
