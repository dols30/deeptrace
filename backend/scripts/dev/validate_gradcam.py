"""Grad-CAM sanity checks on more than one face.

Runs in the model virtualenv. Prints one JSON object. Exits 0 when every scored
face changes its map with the target class and the maps differ across faces.
Occlusion wins and losses are both reported. A loss does not by itself fail
the run.

  backend/.venv-models/bin/python backend/scripts/dev/validate_gradcam.py \
    --repo backend/vendor/DeepfakeBench \
    --weights backend/models/efficientnetb4/effnb4_best.pth \
    --landmarks backend/models/efficientnetb4/shape_predictor_81_face_landmarks.dat \
    --images image_a.jpg image_b.jpg
"""
import argparse
import importlib.util
import json
import sys
from pathlib import Path

INFERENCE = Path(__file__).resolve().parents[1] / "inference"
sys.path.insert(0, str(INFERENCE))


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def flat(heatmap):
    return [value for row in heatmap for value in row]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--landmarks", type=Path, required=True)
    parser.add_argument("--images", type=Path, nargs="+", required=True)
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    args = parser.parse_args()
    repo = args.repo.resolve()
    sys.path.insert(0, str(repo / "training"))
    import cv2
    import dlib
    import numpy as np
    import torch
    from face_geometry import align_face
    from gradcam import attribution_record

    network = load_module("deeptrace_effnet_validate", repo / "training/networks/efficientnetb4.py")
    preprocessing = load_module("deeptrace_face_validate", repo / "preprocessing/preprocess.py")
    model = network.EfficientNetB4(dict(num_classes=2, inc=3, dropout=False, mode="Original", pretrained=False))
    state = torch.load(str(args.weights), map_location="cpu", weights_only=True)
    state = state.get("state_dict", state)
    state = {key.removeprefix("module."): value for key, value in state.items()}
    state = {key.removeprefix("backbone."): value for key, value in state.items()}
    model.load_state_dict(state, strict=True)
    model.to(args.device).eval()
    detector = dlib.get_frontal_face_detector()
    predictor = dlib.shape_predictor(str(args.landmarks))

    faces = []
    skipped = []
    for image_path in args.images:
        image = cv2.imread(str(image_path))
        if image is None:
            skipped.append({"path": image_path.name, "reason": "unreadable"})
            continue
        aligned = align_face(preprocessing, detector, predictor, image, res=256)
        if aligned is None:
            skipped.append({"path": image_path.name, "reason": "no alignable face"})
            continue
        rgb = cv2.cvtColor(aligned["crop"], cv2.COLOR_BGR2RGB).astype(np.float32) / 255
        tensor = torch.from_numpy(((rgb - 0.5) / 0.5).transpose(2, 0, 1).copy()).unsqueeze(0).to(args.device)
        record, _, score = attribution_record(model, tensor, aligned, image, None, image_path.stem, sanity=True)
        faces.append({
            "path": image_path.name,
            "screening_score": round(score, 6),
            "target_class_changes_map": record["sanity"]["target_class_changes_map"],
            "occlusion": record["sanity"]["occlusion"],
            "heatmap": record["heatmap"],
        })

    maps_differ = False
    if len(faces) >= 2:
        maps_differ = any(flat(faces[0]["heatmap"]) != flat(other["heatmap"]) for other in faces[1:])
    occlusion_wins = sum(1 for face in faces if face["occlusion"].get("high_exceeds_low") is True)
    occlusion_losses = sum(1 for face in faces if face["occlusion"].get("high_exceeds_low") is False)
    class_changes = all(face["target_class_changes_map"] for face in faces) if faces else False
    report = {
        "scored_faces": len(faces),
        "skipped": skipped,
        "target_class_changes_map": class_changes,
        "maps_differ_across_faces": maps_differ,
        "occlusion_high_exceeds_low": occlusion_wins,
        "occlusion_high_does_not_exceed_low": occlusion_losses,
        "faces": [{key: value for key, value in face.items() if key != "heatmap"} | {
            "heatmap_peak_index": divmod(int(np.argmax(flat(face["heatmap"]))), 8),
        } for face in faces],
    }
    print(json.dumps(report, indent=2))
    if len(faces) < 2 or not class_changes or not maps_differ:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
