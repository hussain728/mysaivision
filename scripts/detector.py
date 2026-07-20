#!/usr/bin/env python3
"""Store Vision — Phase 1 clip analyzer.

Runs the exported YOLOX-S ONNX model over a video clip with ONNX Runtime and
reports, per clip:
  - total detections per class
  - average confidence for `person` detections
  - average inference time per frame (model forward pass only)
  - frames where a person is *likely visible but not detected at threshold*
    (a heuristic, see below), plus temporal-gap flicker misses

It also writes a watchable H.264 annotated video (all kept detections drawn).

Missed-person heuristic (no hand-labeled ground truth exists, so this is an
automated proxy, not a guarantee):
  * WEAK person  = a person detection with  low_thr <= conf < score_thr.
    The model sees a person but not confidently enough to fire at the working
    threshold -> a near-miss / weak detection worth surfacing.
  * GAP miss     = zero persons at score_thr in frame i, but >=1 person at
    score_thr in BOTH neighbours i-1 and i+1 -> a flicker/drop-out.

Requires the YOLOX repo root on PYTHONPATH:
    PYTHONPATH=agent/YOLOX python scripts/detector.py \
        --model models/yolox_s.onnx --video test_footage/clip.mp4
"""
import argparse
import json
import os
import time
from collections import Counter, defaultdict

import cv2
import imageio.v2 as imageio
import numpy as np
import onnxruntime

from yolox.data.data_augment import preproc as preprocess
from yolox.data.datasets import COCO_CLASSES
from yolox.utils import demo_postprocess, multiclass_nms

# --- DESIGN §2.5 detection overlay palette (BGR for OpenCV) ----------------
# Color encodes meaning first, class second. Confident detections take their
# class color; sub-threshold ones render grey 1px with no label (debug-visible,
# feel-invisible). Alert amber (#FFB347) and confirmed-theft red (#FF5C4D) are
# applied by the agent once zones + verdicts exist (Phase 4+), not here.
_C = {
    "person":    (255, 168, 78),   # #4EA8FF blue
    "vehicle":   (250, 139, 167),  # #A78BFA violet
    "bag":       (182, 114, 244),  # #F472B6 pink
    "inventory": (191, 212, 45),   # #2DD4BF teal
    "weak":      (128, 114, 107),  # #6B7280 grey — low-confidence / unmapped
}
_GROUP = {"person": "person"}
_GROUP.update({n: "vehicle" for n in ("car", "truck", "bus", "motorcycle", "bicycle")})
# 'bag' is our fine-tuned class; handbag/backpack/suitcase are its COCO sources
_GROUP.update({n: "bag" for n in ("bag", "handbag", "backpack", "suitcase")})
_GROUP.update({n: "inventory" for n in ("box", "packet")})


def _label(img, x, y, text, color):
    """Dark chip + colored text, matching the DESIGN mock."""
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_DUPLEX, 0.5, 1)
    y0 = max(0, y - th - 8)
    cv2.rectangle(img, (x, y0), (x + tw + 8, y0 + th + 8), (24, 20, 16), -1)
    cv2.putText(img, text, (x + 4, y0 + th + 3),
                cv2.FONT_HERSHEY_DUPLEX, 0.5, color, 1, cv2.LINE_AA)


def draw_detections(frame, dets, class_names, score_thr):
    """Render detections per DESIGN §2.5: class color + label for confident
    detections, grey 1px (no label) for sub-threshold ones."""
    for x1, y1, x2, y2, score, cls in dets:
        ci = int(cls)
        name = class_names[ci] if ci < len(class_names) else str(ci)
        p1, p2 = (int(x1), int(y1)), (int(x2), int(y2))
        if score < score_thr:
            cv2.rectangle(frame, p1, p2, _C["weak"], 1)      # low-confidence
            continue
        group = _GROUP.get(name)
        color = _C[group] if group else _C["weak"]           # unmapped -> grey
        cv2.rectangle(frame, p1, p2, color, 2)
        _label(frame, int(x1), int(y1), f"{name} {score:.2f}", color)
    return frame


def analyze(model, video, output, score_thr, low_thr, nms_thr, input_size, draw,
            class_names=None):
    names = list(class_names) if class_names else list(COCO_CLASSES)
    pid = names.index("person") if "person" in names else -1
    sess = onnxruntime.InferenceSession(model, providers=["CPUExecutionProvider"])
    in_name = sess.get_inputs()[0].name

    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        raise SystemExit(f"cannot open {video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    writer = None
    if draw and output:
        os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
        writer = imageio.get_writer(output, fps=fps, codec="libx264",
                                    quality=7, macro_block_size=None)

    class_totals = Counter()          # per-class detections at score_thr
    person_confs = []                 # confidences of persons at score_thr
    infer_times = []                  # seconds per frame (forward only)
    persons_per_frame = []            # count at score_thr, indexed by frame
    weak_frames = []                  # (frame, timestamp_s, weak_conf)

    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        img, ratio = preprocess(frame, input_size)

        t0 = time.perf_counter()
        out = sess.run(None, {in_name: img[None, :, :, :].astype(np.float32)})[0]
        infer_times.append(time.perf_counter() - t0)

        preds = demo_postprocess(out, input_size)[0]
        b, s = preds[:, :4], preds[:, 4:5] * preds[:, 5:]
        xyxy = np.empty_like(b)
        xyxy[:, 0] = b[:, 0] - b[:, 2] / 2
        xyxy[:, 1] = b[:, 1] - b[:, 3] / 2
        xyxy[:, 2] = b[:, 0] + b[:, 2] / 2
        xyxy[:, 3] = b[:, 1] + b[:, 3] / 2
        xyxy /= ratio

        dets = multiclass_nms(xyxy, s, nms_thr=nms_thr, score_thr=low_thr)
        if dets is None:
            dets = np.zeros((0, 6), dtype=np.float32)

        conf = dets[:, 4]
        cls = dets[:, 5].astype(int)
        strong = conf >= score_thr

        # per-class totals (strong only)
        for c in cls[strong]:
            class_totals[names[c]] += 1

        # person stats
        is_person = cls == pid
        strong_person = is_person & strong
        weak_person = is_person & (conf < score_thr)  # low_thr<=conf<score_thr
        person_confs.extend(conf[strong_person].tolist())
        persons_per_frame.append(int(strong_person.sum()))
        if weak_person.any() and not strong_person.any():
            weak_frames.append((idx, round(idx / fps, 2),
                                round(float(conf[weak_person].max()), 3)))

        if writer is not None:
            annotated = draw_detections(frame.copy(), dets, names, score_thr)
            writer.append_data(cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB))

        idx += 1

    cap.release()
    if writer is not None:
        writer.close()

    # temporal-gap flicker misses
    gap_frames = []
    for i in range(1, len(persons_per_frame) - 1):
        if (persons_per_frame[i] == 0
                and persons_per_frame[i - 1] > 0
                and persons_per_frame[i + 1] > 0):
            gap_frames.append((i, round(i / fps, 2)))

    return {
        "video": video,
        "frames": idx,
        "fps": round(fps, 2),
        "resolution": f"{width}x{height}",
        "score_thr": score_thr,
        "low_thr": low_thr,
        "class_totals": dict(class_totals.most_common()),
        "person_detections": len(person_confs),
        "person_avg_conf": round(float(np.mean(person_confs)), 4) if person_confs else None,
        "avg_infer_ms": round(float(np.mean(infer_times)) * 1000, 2),
        "effective_fps": round(1.0 / float(np.mean(infer_times)), 2) if infer_times else None,
        "weak_person_frames": weak_frames,
        "gap_person_frames": gap_frames,
        "annotated_output": output if draw else None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="models/yolox_s.onnx")
    ap.add_argument("--video", required=True)
    ap.add_argument("--output", default=None,
                    help="annotated H.264 mp4 path (default: <clip>__annotated.mp4)")
    ap.add_argument("--score", type=float, default=0.30)
    ap.add_argument("--low", type=float, default=0.10)
    ap.add_argument("--nms", type=float, default=0.45)
    ap.add_argument("--tsize", type=int, default=640)
    ap.add_argument("--classes", default=None,
                    help="class-names file (one per line); default COCO-80. "
                         "Use finetune/classes.txt for the fine-tuned model.")
    ap.add_argument("--no-draw", action="store_true")
    args = ap.parse_args()

    output = args.output
    if output is None and not args.no_draw:
        base = os.path.splitext(args.video)[0]
        output = f"{base}__annotated.mp4"

    class_names = None
    if args.classes:
        with open(args.classes) as f:
            class_names = [ln.strip() for ln in f
                           if ln.strip() and not ln.strip().startswith("#")]

    r = analyze(args.model, args.video, output, args.score, args.low,
                args.nms, (args.tsize, args.tsize), draw=not args.no_draw,
                class_names=class_names)
    print(json.dumps(r, indent=2))


if __name__ == "__main__":
    main()
