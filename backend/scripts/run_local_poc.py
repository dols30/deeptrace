"""Opt into the extended local PoC without changing portable model defaults or credentials."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
from deeptrace.config import settings

commands = {
    "DEEPTRACE_EFFICIENTNET_DECISION_RULE": settings.efficientnet_decision_rule if settings.efficientnet_decision_rule != "default_0_5" else "ffpp_c23_kaggle_v1",
    "DEEPTRACE_EFFICIENTNET_COMMAND": settings.efficientnet_command or ".venv-models/bin/python scripts/inference/efficientnetb4.py --repo vendor/DeepfakeBench --weights models/efficientnetb4/effnb4_best.pth --landmarks models/efficientnetb4/shape_predictor_81_face_landmarks.dat --frames {frames_dir} --device cpu",
    "DEEPTRACE_SCENE_COMMAND": settings.scene_command or ".venv-models/bin/python scripts/inference/commfor.py --weights models/commfor/frontier.safetensors --config models/commfor/config.json --revision 16db135220b318d811b207db576d90368980b595 --frames {frames_dir} --device cpu",
    "DEEPTRACE_AASIST_COMMAND": settings.aasist_command or (
        ".venv-models/bin/python scripts/inference/aasist.py --repo vendor/aasist --weights models/aasist/"
        + ("AASIST-L.pth" if settings.audio_model == "aasist-l" else "AASIST.pth")
        + " --variant " + ("aasist-l" if settings.audio_model == "aasist-l" else "aasist") + " --audio {audio_path} --device cpu"),
    "DEEPTRACE_REVIEW_SIGNALS_COMMAND": settings.review_signals_command or ".venv-models/bin/python scripts/inference/review_signals.py --media {media_path} --landmarks models/efficientnetb4/shape_predictor_81_face_landmarks.dat --max-seconds 30",
    "DEEPTRACE_AASIST_WINDOW_MODE": "full",
    "DEEPTRACE_GAN_ARTIFACT_COMMAND": settings.gan_artifact_command or ".venv-models/bin/python scripts/inference/cnn_artifacts.py --repo vendor/CNNDetection --weights models/cnn_artifacts/blur_jpg_prob0.5.pth --frames {frames_dir} --device cpu",
    "DEEPTRACE_VOCODER_ARTIFACT_COMMAND": settings.vocoder_artifact_command or ".venv-models/bin/python scripts/inference/lfcc_lcnn.py --repo vendor/asvspoof2021 --weights models/lfcc_lcnn/df_trained_network.pt --audio {audio_path} --device cpu",
    "DEEPTRACE_MICRO_EXPRESSION_COMMAND": settings.micro_expression_command or ".venv-models/bin/python scripts/inference/softnet.py --repo vendor/SoftNet-SpotME --weights models/softnet/CASME_micro_s1.hdf5 --landmarks vendor/SoftNet-SpotME/Utils/shape_predictor_68_face_landmarks.dat --media {media_path} --max-seconds 30",
}
for key,value in commands.items():
    os.environ.setdefault(key,value)
print("Extended local PoC: artifact detectors, micro-expression spotting, full audio windows and review measurements enabled. Authentication settings are preserved.",flush=True)
os.execv(sys.executable,[sys.executable,"-m","uvicorn","deeptrace.main:app","--host","127.0.0.1","--port",os.environ.get("PORT","8000")])
