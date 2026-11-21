"""Load configured model assets without requiring sample media."""
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def require(path: Path) -> None:
    if not path.is_file():
        raise SystemExit(f"Missing required asset: {path.relative_to(ROOT)}")


def main() -> None:
    require(ROOT / "models/aasist/AASIST.pth")
    require(ROOT / "models/efficientnetb4/effnb4_best.pth")
    require(ROOT / "models/efficientnetb4/shape_predictor_81_face_landmarks.dat")
    for repo in (ROOT / "vendor/aasist", ROOT / "vendor/DeepfakeBench"):
        if not repo.is_dir():
            raise SystemExit(f"Missing required source: {repo.relative_to(ROOT)}")

    import cv2  # noqa: F401
    import dlib
    import librosa  # noqa: F401
    import numpy as np  # noqa: F401
    import torch

    dlib.shape_predictor(str(ROOT / "models/efficientnetb4/shape_predictor_81_face_landmarks.dat"))
    checks = [
        [sys.executable, str(ROOT / "scripts/inference/aasist.py"), "--help"],
        [sys.executable, str(ROOT / "scripts/inference/efficientnetb4.py"), "--help"],
    ]
    for command in checks:
        subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
    print(f"Model runtime ready: torch={torch.__version__}; device=cpu")


if __name__ == "__main__":
    main()
