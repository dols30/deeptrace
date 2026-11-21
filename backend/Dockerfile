FROM python:3.11-slim-bookworm AS model-builder

RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Retries=5 update \
    && apt-get -o Acquire::Retries=5 install -y --no-install-recommends build-essential cmake \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt requirements-models-cpu.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-models-cpu.txt

FROM python:3.11-slim-bookworm

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

ENV DEEPTRACE_UPLOAD_DIR=/tmp/deeptrace-uploads
ENV DEEPTRACE_REPORT_DB_PATH=/data/deeptrace.db
ENV DEEPTRACE_REPORT_MEDIA_DIR=/data/report-media
ENV DEEPTRACE_VIDEO_MODEL=efficientnetb4
ENV DEEPTRACE_AUDIO_MODEL=aasist
ENV DEEPTRACE_EFFICIENTNET_COMMAND="python /app/scripts/inference/efficientnetb4.py --repo /app/vendor/DeepfakeBench --weights /app/models/efficientnetb4/effnb4_best.pth --landmarks /app/models/efficientnetb4/shape_predictor_81_face_landmarks.dat --frames {frames_dir} --device cpu"
ENV DEEPTRACE_SCENE_COMMAND="python /app/scripts/inference/commfor.py --weights /app/models/commfor/frontier.safetensors --config /app/models/commfor/config.json --revision 16db135220b318d811b207db576d90368980b595 --frames {frames_dir} --device cpu"
ENV DEEPTRACE_AASIST_COMMAND="python /app/scripts/inference/aasist.py --repo /app/vendor/aasist --weights /app/models/aasist/AASIST.pth --audio {audio_path} --variant aasist --device cpu"

EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=6 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=2)"
CMD ["uvicorn", "deeptrace.main:app", "--host", "0.0.0.0", "--port", "8080"]
