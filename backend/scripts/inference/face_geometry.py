"""Similarity warp used by DeepfakeBench face alignment, with the matrix kept.

The vendor function extract_aligned_face_dlib computes this matrix and discards it.
The destination template and scale match preprocessing.preprocess.img_align_crop.
"""
import numpy as np


def similarity_matrix(landmarks, outsize=256, scale=1.3):
    """Return the 2x3 matrix DeepfakeBench passes to cv2.warpAffine."""
    from skimage import transform as trans

    target_size = [112, 112]
    destination = np.array([
        [30.2946, 51.6963],
        [65.5318, 51.5014],
        [48.0252, 71.7366],
        [33.5493, 92.3655],
        [62.7299, 92.2041],
    ], dtype=np.float32)
    if target_size[1] == 112:
        destination[:, 0] += 8.0
    destination[:, 0] = destination[:, 0] * outsize / target_size[0]
    destination[:, 1] = destination[:, 1] * outsize / target_size[1]
    margin_rate = scale - 1
    x_margin = outsize * margin_rate / 2.0
    y_margin = outsize * margin_rate / 2.0
    destination[:, 0] += x_margin
    destination[:, 1] += y_margin
    destination[:, 0] *= outsize / (outsize + 2 * x_margin)
    destination[:, 1] *= outsize / (outsize + 2 * y_margin)
    transform = trans.SimilarityTransform()
    transform.estimate(np.asarray(landmarks, dtype=np.float32), destination)
    return np.asarray(transform.params[0:2, :], dtype=np.float64)


def warp_rgb(rgb, matrix, res=256):
    import cv2
    warped = cv2.warpAffine(rgb, matrix, (res, res))
    return cv2.resize(warped, (res, res))


def align_face(preprocessing, detector, predictor, image_bgr, res=256):
    """Return the official crop plus the matrix that produced it.

    The crop is the one extract_aligned_face_dlib would score. The matrix is
    checked against that crop and rejected if the two warps differ.
    """
    import cv2

    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    faces = detector(rgb, 1)
    if not len(faces):
        return None
    face = max(faces, key=lambda rect: rect.width() * rect.height())
    landmarks = preprocessing.get_keypts(rgb, face, predictor, detector)
    matrix = similarity_matrix(landmarks, res)
    official, _, _ = preprocessing.extract_aligned_face_dlib(detector, predictor, image_bgr, res=res)
    if official is None:
        return None
    ours = cv2.cvtColor(warp_rgb(rgb, matrix, res), cv2.COLOR_RGB2BGR)
    if ours.shape != official.shape or int(np.max(np.abs(ours.astype(np.int16) - official.astype(np.int16)))) != 0:
        raise RuntimeError("Face warp does not match DeepfakeBench extract_aligned_face_dlib")
    height, width = image_bgr.shape[:2]
    return {
        "crop": official,
        "matrix": matrix,
        "landmarks": np.asarray(landmarks, dtype=np.float64),
        "frame_width": int(width),
        "frame_height": int(height),
        "crop_size": int(res),
    }
