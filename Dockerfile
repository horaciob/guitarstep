# guitarr web UI in a container.
#
# Dependencies are installed by scripts/install-linux.sh (shared with CI): basic-pitch runs
# its bundled ONNX model through onnxruntime, because its TensorFlow dependency on Linux
# clashes with the pinned NumPy 2.x.
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
COPY scripts/install-linux.sh scripts/
RUN scripts/install-linux.sh --deps-only

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
