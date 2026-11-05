#!/usr/bin/env bash
# Installs guitarr's Python dependencies on Linux (CI and Docker).
#
# basic-pitch 0.4.0 requires TensorFlow on Linux, which needs NumPy 1.x and clashes with the
# pinned NumPy 2.x. We install it without dependencies and run its bundled ONNX model with
# onnxruntime instead (same model, different runtime).
#
# Usage: scripts/install-linux.sh [--dev] [--deps-only]
set -euo pipefail
cd "$(dirname "$0")/.."

skip='^(basic-pitch|pytest|httpx|playwright|axe-playwright)'
project=1
for arg in "$@"; do
  case "$arg" in
    --dev) skip='^basic-pitch' ;;
    --deps-only) project=0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done
grep -vE "$skip" requirements.txt > /tmp/guitarr-requirements.txt
pip install -r /tmp/guitarr-requirements.txt
pip install --no-deps basic-pitch==0.4.0
pip install "mir_eval==0.8.2" "resampy==0.4.2" "scikit-learn==1.9.1" "typing_extensions==4.16.0" "onnxruntime==1.31.1"
if [[ $project == 1 ]]; then pip install --no-deps -e .; fi
