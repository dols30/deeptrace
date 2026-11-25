FROM python:3.11-slim-bookworm AS model-builder

RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Retries=5 update \
    && apt-get -o Acquire::Retries=5 install -y --no-install-recommends build-essential cmake \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt requirements-models-cpu.txt ./
# PyTorch wheel index: "cpu" (default) or a CUDA variant such as "cu126" for GPU hosts.
# Docker builds cannot see the GPU, so this is chosen explicitly, not auto-detected.
# The plain PyPI torch wheel on x86_64 Linux is a CUDA build that pulls several GB of
# nvidia-* wheels; pinning the index keeps CPU images small. The +cpu/+cuXXX builds
# satisfy the ==2.7.1 / ==0.22.1 pins in requirements-models-cpu.txt.
ARG TORCH_INDEX=cpu
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/${TORCH_INDEX} \
        torch==2.7.1 torchvision==0.22.1 \
    && pip install --no-cache-dir -r requirements.txt -r requirements-models-cpu.txt

# Runtime image with the three default detectors. docker-compose.yml builds the target named in
# DEEPTRACE_MODEL_PROFILE: "core" (default) or "all-models".
FROM python:3.11-slim-bookworm AS core

RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Retries=5 update \
    && apt-get -o Acquire::Retries=5 install -y --no-install-recommends ffmpeg libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=model-builder /usr/local /usr/local
COPY deeptrace ./deeptrace
COPY scripts ./scripts
COPY vendor/aasist ./vendor/aasist
COPY vendor/DeepfakeBench ./vendor/DeepfakeBench
COPY models ./models

# Device passed to every model runner: "cpu" (default) or "cuda" (requires a CUDA TORCH_INDEX
# and a GPU exposed to the container, see docker-compose.gpu.yml).
ARG DEEPTRACE_DEVICE=cpu
ENV DEEPTRACE_UPLOAD_DIR=/tmp/deeptrace-uploads
ENV DEEPTRACE_REPORT_DB_PATH=/data/deeptrace.db
ENV DEEPTRACE_REPORT_MEDIA_DIR=/data/report-media
ENV DEEPTRACE_VIDEO_MODEL=efficientnetb4
ENV DEEPTRACE_AUDIO_MODEL=aasist
ENV DEEPTRACE_EFFICIENTNET_COMMAND="python /app/scripts/inference/efficientnetb4.py --repo /app/vendor/DeepfakeBench --weights /app/models/efficientnetb4/effnb4_best.pth --landmarks /app/models/efficientnetb4/shape_predictor_81_face_landmarks.dat --frames {frames_dir} --device ${DEEPTRACE_DEVICE}"
ENV DEEPTRACE_SCENE_COMMAND="python /app/scripts/inference/commfor.py --weights /app/models/commfor/frontier.safetensors --config /app/models/commfor/config.json --revision 16db135220b318d811b207db576d90368980b595 --frames {frames_dir} --device ${DEEPTRACE_DEVICE}"
ENV DEEPTRACE_AASIST_COMMAND="python /app/scripts/inference/aasist.py --repo /app/vendor/aasist --weights /app/models/aasist/AASIST.pth --audio {audio_path} --variant aasist --device ${DEEPTRACE_DEVICE}"

EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=6 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=2)"
CMD ["uvicorn", "deeptrace.main:app", "--host", "0.0.0.0", "--port", "8080"]

# All-model PoC profile (docs/ALL_MODELS_SETUP.md): the core image plus CNNDetection, LFCC-LCNN,
# SOFTNet and the review measurements. Opt in with DEEPTRACE_MODEL_PROFILE=all-models.
FROM core AS all-models
# Must match the core stage ("cpu" or e.g. "cu126"); compose passes the same value to both.
ARG TORCH_INDEX=cpu
ARG DEEPTRACE_DEVICE=cpu
COPY requirements-models-all.txt /app/requirements-models-all.txt
RUN pip uninstall -y opencv-python-headless \
    && pip install --no-cache-dir --index-url https://download.pytorch.org/whl/${TORCH_INDEX} torchaudio==2.7.1 \
    && pip install --no-cache-dir -r /app/requirements-models-all.txt \
    && pip check
# backend/models is already copied by the core stage.
COPY vendor/aasist/.deeptrace-revision /app/vendor/aasist/.deeptrace-revision
COPY vendor/DeepfakeBench/.deeptrace-revision /app/vendor/DeepfakeBench/.deeptrace-revision
COPY vendor/CNNDetection /app/vendor/CNNDetection
COPY vendor/asvspoof2021 /app/vendor/asvspoof2021
COPY vendor/SoftNet-SpotME/training.py vendor/SoftNet-SpotME/extraction_preprocess.py vendor/SoftNet-SpotME/README.md vendor/SoftNet-SpotME/.deeptrace-revision /app/vendor/SoftNet-SpotME/
COPY vendor/SoftNet-SpotME/Utils/shape_predictor_68_face_landmarks.dat /app/vendor/SoftNet-SpotME/Utils/shape_predictor_68_face_landmarks.dat
COPY model-assets.all.json /app/model-assets.all.json
COPY scripts/verify_all_models.py /app/scripts/verify_all_models.py
# Profile settings, unchanged from the former docker-compose.all-models.yml. They define what the
# scores mean (docs/MODEL_REGISTRY.md), so they live with the image rather than in .env.
ENV DEEPTRACE_AASIST_WINDOW_MODE=full
ENV DEEPTRACE_EFFICIENTNET_DECISION_RULE=ffpp_c23_kaggle_v1
ENV DEEPTRACE_FRAME_INTERVAL_SECONDS=1
ENV DEEPTRACE_MAX_FRAMES=120
ENV DEEPTRACE_GAN_ARTIFACT_COMMAND="python /app/scripts/inference/cnn_artifacts.py --repo /app/vendor/CNNDetection --weights /app/models/cnn_artifacts/blur_jpg_prob0.5.pth --frames {frames_dir} --device ${DEEPTRACE_DEVICE}"
ENV DEEPTRACE_VOCODER_ARTIFACT_COMMAND="python /app/scripts/inference/lfcc_lcnn.py --repo /app/vendor/asvspoof2021 --weights /app/models/lfcc_lcnn/df_trained_network.pt --audio {audio_path} --device ${DEEPTRACE_DEVICE}"
ENV DEEPTRACE_REVIEW_SIGNALS_COMMAND="python /app/scripts/inference/review_signals.py --media {media_path} --landmarks /app/models/efficientnetb4/shape_predictor_81_face_landmarks.dat --max-seconds 30"
ENV DEEPTRACE_MICRO_EXPRESSION_COMMAND="python /app/scripts/inference/softnet.py --repo /app/vendor/SoftNet-SpotME --weights /app/models/softnet/CASME_micro_s1.hdf5 --landmarks /app/vendor/SoftNet-SpotME/Utils/shape_predictor_68_face_landmarks.dat --media {media_path} --max-seconds 30"
ENV OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 TF_NUM_INTEROP_THREADS=1 TF_NUM_INTRAOP_THREADS=2

# A plain `docker build ./backend` (no --target) still produces the core image.
FROM core
