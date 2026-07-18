#!/usr/bin/env python3
"""Store Vision — Phase 1 video detection.

Runs the exported YOLOX-S ONNX model over a video clip with ONNX Runtime,
keeps only the Store Vision classes (person / vehicles / box-like), draws a
labelled box + confidence on every kept detection, writes an annotated output
video, and prints a running per-class count.

Detection correctness comes from reusing YOLOX's own pipeline:
  - `preproc`            -> letterbox resize to 640 (keeps aspect, pads)
  - `demo_postprocess`   -> decode the raw grid outputs to boxes
  - `multiclass_nms`     -> per-class NMS
  - `vis`                -> YOLOX's box/label drawing

Requires the YOLOX repo root on PYTHONPATH, e.g.:
    PYTHONPATH=third_party/YOLOX python scripts/detect_video.py \
        --model models/yolox_s.onnx --video data/clip.mp4 \
        --output outputs/clip_annotated.mp4
"""
import argparse
import os
import time
from collections import Counter

import cv2
import numpy as np
import onnxruntime

from yolox.data.data_augment import preproc as preprocess
from yolox.data.datasets import COCO_CLASSES
from yolox.utils import demo_postprocess, multiclass_nms, vis

# --- Store Vision Phase 1 classes (SPEC §3) --------------------------------
PERSON = {"person"}
VEHICLES = {"car", "truck", "bus", "motorcycle", "bicycle"}
# COCO-80 has no literal "box"/"packet" class. The nearest boxy/parcel-shaped
# COCO classes stand in for inventory objects on the pretrained model; real
# box/packet detection is the light fine-tuning the SPEC calls out for later.
BOX_LIKE = {"suitcase", "backpack", "handbag"}

KEEP = PERSON | VEHICLES | BOX_LIKE
KEEP_IDS = {i for i, n in enumerate(COCO_CLASSES) if n in KEEP}


def build_session(model_path: str) -> onnxruntime.InferenceSession:
    so = onnxruntime.SessionOptions()
    so.intra_op_num_threads = os.cpu_count() or 4
    so.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
    return onnxruntime.InferenceSession(
        model_path, sess_options=so, providers=["CPUExecutionProvider"]
    )


def detect(session, frame, input_shape, score_thr, nms_thr, keep_ids=None):
    """Return (boxes_xyxy, scores, cls_ids) for kept classes, or (None, None, None)."""
    if keep_ids is None:
        keep_ids = KEEP_IDS
    img, ratio = preprocess(frame, input_shape)
    out = session.run(None, {session.get_inputs()[0].name: img[None, :, :, :]})[0]
    preds = demo_postprocess(out, input_shape)[0]

    boxes = preds[:, :4]
    scores = preds[:, 4:5] * preds[:, 5:]

    xyxy = np.ones_like(boxes)
    xyxy[:, 0] = boxes[:, 0] - boxes[:, 2] / 2.0
    xyxy[:, 1] = boxes[:, 1] - boxes[:, 3] / 2.0
    xyxy[:, 2] = boxes[:, 0] + boxes[:, 2] / 2.0
    xyxy[:, 3] = boxes[:, 1] + boxes[:, 3] / 2.0
    xyxy /= ratio

    dets = multiclass_nms(xyxy, scores, nms_thr=nms_thr, score_thr=score_thr)
    if dets is None:
        return None, None, None

    b, s, c = dets[:, :4], dets[:, 4], dets[:, 5].astype(int)
    mask = np.array([cid in keep_ids for cid in c], dtype=bool)
    if not mask.any():
        return None, None, None
    return b[mask], s[mask], c[mask]


def main() -> None:
    ap = argparse.ArgumentParser(description="YOLOX ONNX video detection (Phase 1)")
    ap.add_argument("--model", default="models/yolox_s.onnx")
    ap.add_argument("--video", default="data/clip.mp4")
    ap.add_argument("--output", default="outputs/clip_annotated.mp4")
    ap.add_argument("--score", type=float, default=0.35)
    ap.add_argument("--nms", type=float, default=0.45)
    ap.add_argument("--input-shape", default="640,640")
    ap.add_argument("--log-every", type=int, default=100, help="frames between running-count logs")
    ap.add_argument("--classes", default=None,
                    help="comma-separated class names to keep (overrides the default "
                         "person/vehicle/box-like set). e.g. --classes bottle,cup,book,handbag")
    ap.add_argument("--class-names-file", default=None,
                    help="text file of class names (one per line) for a custom/fine-tuned "
                         "model whose classes differ from COCO. Defaults to the 80 COCO names.")
    args = ap.parse_args()

    h, w = (int(x) for x in args.input_shape.split(","))
    input_shape = (h, w)

    # class names: COCO by default, or a custom list for a fine-tuned model
    if args.class_names_file:
        with open(args.class_names_file) as f:
            class_names = [ln.strip() for ln in f
                           if ln.strip() and not ln.strip().startswith("#")]
    else:
        class_names = list(COCO_CLASSES)

    if args.classes:
        wanted = {c.strip() for c in args.classes.split(",") if c.strip()}
        unknown = wanted - set(class_names)
        if unknown:
            raise SystemExit(f"unknown class(es) for this model: {sorted(unknown)}")
        keep_ids = {i for i, n in enumerate(class_names) if n in wanted}
        keep_names = wanted
    elif args.class_names_file:
        keep_ids = set(range(len(class_names)))   # custom model: keep all its classes
        keep_names = set(class_names)
    else:
        keep_ids = KEEP_IDS
        keep_names = KEEP

    session = build_session(args.model)

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise SystemExit(f"could not open video: {args.video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    writer = cv2.VideoWriter(args.output, cv2.VideoWriter_fourcc(*"mp4v"), fps, (W, H))
    if not writer.isOpened():
        raise SystemExit("could not open VideoWriter (codec issue)")

    counts = Counter()            # total kept detections per class over the clip
    frames_with_det = 0
    t0 = time.time()
    idx = 0
    print(f"Processing {args.video}  ({total} frames, {W}x{H} @ {fps:.1f} fps)")
    print(f"Keeping classes: {sorted(keep_names)}\n")

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        idx += 1

        boxes, scores, cls = detect(session, frame, input_shape, args.score, args.nms, keep_ids)
        if boxes is not None:
            frames_with_det += 1
            for cid in cls:
                counts[class_names[int(cid)]] += 1
            frame = vis(frame, boxes, scores, cls,
                        conf=args.score, class_names=class_names)

        writer.write(frame)

        if idx % args.log_every == 0 or idx == total:
            elapsed = time.time() - t0
            speed = idx / elapsed if elapsed else 0.0
            running = ", ".join(f"{k}:{v}" for k, v in sorted(counts.items())) or "none"
            print(f"[frame {idx:>4}/{total}] {speed:4.1f} fps | running counts -> {running}")

    cap.release()
    writer.release()

    print("\n================ FINAL CLASS COUNTS (total detections) ================")
    if counts:
        width = max(len(k) for k in counts)
        for name, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
            cat = ("person" if name in PERSON else
                   "vehicle" if name in VEHICLES else
                   "box-like" if name in BOX_LIKE else "other")
            print(f"  {name:<{width}}  {n:>7}   ({cat})")
    else:
        print("  (no detections of kept classes)")
    print(f"\nframes with >=1 kept detection: {frames_with_det}/{idx}")
    print(f"annotated video: {args.output}")
    print("note: counts are per-frame detection counts, not unique objects "
          "(object tracking is a later phase).")


if __name__ == "__main__":
    main()
