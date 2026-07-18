#!/usr/bin/env bash
# =============================================================================
# Store Vision — Phase 1: YOLOX detection core, exported to ONNX.
#
# End-to-end reproduction of the Phase 1 build:
#   1. Python 3.12 venv
#   2. clone YOLOX
#   3. install deps WITHOUT the failing onnx-simplifier, then `pip -e .`
#   4. fetch the pretrained yolox_s checkpoint
#   5. export to ONNX (skipping onnx-simplifier)
#   6. run the official ONNX Runtime demo on assets/dog.jpg
#
# Run from the repo root:  bash scripts/setup_phase1.sh
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PY="${PYTHON:-python3.12}"
YOLOX_DIR="third_party/YOLOX"
CKPT="models/yolox_s.pth"
ONNX="models/yolox_s.onnx"
# sha256 of the pretrained COCO yolox_s checkpoint we validated against.
CKPT_SHA256="f55ded7181e1b0c13285c56e7790b8f0e8f8db590fe4edb37f0b7f345c913a30"

mkdir -p third_party models outputs

# --- 1. Python 3.12 virtual environment ------------------------------------
if [ ! -d .venv ]; then
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip

# --- 2. Clone YOLOX --------------------------------------------------------
if [ ! -d "$YOLOX_DIR/.git" ]; then
  git clone --depth 1 https://github.com/Megvii-BaseDetection/YOLOX.git "$YOLOX_DIR"
fi

# --- 3. Install deps (NOT requirements.txt) + YOLOX package ----------------
# onnx-simplifier in YOLOX/requirements.txt fails to build without cmake, so we
# install an explicit, sufficient dependency set instead.
pip install -r requirements-phase1.txt
# --no-build-isolation so the build backend sees the torch we just installed.
pip install --no-deps --no-build-isolation -e "$YOLOX_DIR"

# --- torch >= 2.9 compatibility patch for YOLOX's export script -------------
# torch removed the private torch.onnx._export and made the dynamo exporter the
# default; the patch switches to torch.onnx.export(..., dynamo=False).
if grep -q "torch.onnx._export" "$YOLOX_DIR/tools/export_onnx.py"; then
  git -C "$YOLOX_DIR" apply "$ROOT/scripts/torch213_export_onnx.patch" \
    || echo "WARN: patch did not apply cleanly; check tools/export_onnx.py"
fi

# --- 4. Pretrained checkpoint ----------------------------------------------
# Official source (use this in a normal network environment):
#   https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_s.pth
# If that host is blocked, drop a validated yolox_s.pth into models/ by hand.
if [ ! -f "$CKPT" ]; then
  curl -fSL -o "$CKPT" \
    "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_s.pth" \
    || { echo "ERROR: could not download checkpoint; place a yolox_s.pth in models/"; exit 1; }
fi
echo "checkpoint sha256: $(sha256sum "$CKPT" | awk '{print $1}')  (expected $CKPT_SHA256)"

# --- 5. Export to ONNX (skip onnx-simplifier) ------------------------------
PYTHONPATH="$YOLOX_DIR" python "$YOLOX_DIR/tools/export_onnx.py" \
  --output-name "$ROOT/$ONNX" \
  -n yolox-s \
  -c "$ROOT/$CKPT" \
  --no-onnxsim

# --- 6. Official ONNX Runtime demo on assets/dog.jpg -----------------------
# YOLOX scripts need the repo root on PYTHONPATH or the import fails with
# "No module named yolox".
PYTHONPATH="$YOLOX_DIR" python "$YOLOX_DIR/demo/ONNXRuntime/onnx_inference.py" \
  -m "$ROOT/$ONNX" \
  -i "$YOLOX_DIR/assets/dog.jpg" \
  -o "$ROOT/outputs" \
  -s 0.3 \
  --input_shape 640,640

# Pretty-print the detected objects + confidence scores.
PYTHONPATH="$YOLOX_DIR" python scripts/run_inference.py \
  --model "$ROOT/$ONNX" \
  --image "$YOLOX_DIR/assets/dog.jpg" \
  --score 0.3

echo
echo "Done. Annotated image: outputs/dog.jpg"
