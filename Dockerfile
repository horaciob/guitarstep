# guitarr web UI in a container.
#
# basic-pitch 0.4.0 pulls TensorFlow on Linux, which needs NumPy 1.x and clashes with the
# pinned NumPy 2.x. In the image we install it without dependencies and run its bundled
# ONNX model through onnxruntime instead (same model, different runtime).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    GUITARR_HOME=/data

# PortAudio (sounddevice), libsndfile (soundfile), ffmpeg (m4a and other compressed takes).
RUN apt-get update \
 && apt-get install -y --no-install-recommends libportaudio2 libsndfile1 ffmpeg \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN grep -vE '^(basic-pitch|pytest|httpx)' requirements.txt > /tmp/requirements.txt \
 && pip install -r /tmp/requirements.txt \
 && pip install --no-deps basic-pitch==0.4.0 \
 && pip install "mir_eval==0.8.2" "resampy==0.4.2" "scikit-learn==1.9.1" "typing_extensions==4.16.0" "onnxruntime==1.31.1"

COPY pyproject.toml README.md ./
COPY guitarr ./guitarr
RUN pip install --no-deps .

RUN useradd --create-home --uid 1000 guitarr \
 && mkdir -p /data && chown guitarr:guitarr /data
USER guitarr
VOLUME ["/data"]

EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/status', timeout=4)" || exit 1

CMD ["guitarr", "gui", "--host", "0.0.0.0", "--port", "8765", "--no-browser"]
