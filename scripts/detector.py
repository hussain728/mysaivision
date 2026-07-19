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
from yolox.utils import demo_postprocess, multiclass_nms, vis

PERSON_ID = COCO_CLASSES.index("person")


def analyze(model, video, output, score_thr, low_thr, nms_thr, input_size, draw):
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
            class_totals[COCO_CLASSES[c]] += 1

        # person stats
        is_person = cls == PERSON_ID
        strong_person = is_person & strong
        weak_person = is_person & (conf < score_thr)  # low_thr<=conf<score_thr
        person_confs.extend(conf[strong_person].tolist())
        persons_per_frame.append(int(strong_person.sum()))
        if weak_person.any() and not strong_person.any():
            weak_frames.append((idx, round(idx / fps, 2),
                                round(float(conf[weak_person].max()), 3)))

        if writer is not None:
            m = strong
            vis_img = vis(frame.copy(), dets[m, :4], dets[m, 4],
                          dets[m, 5].astype(int), conf=score_thr,
                          class_names=COCO_CLASSES)
            writer.append_data(cv2.cvtColor(vis_img, cv2.COLOR_BGR2RGB))

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
    ap.add_argument("--no-draw", action="store_true")
    args = ap.parse_args()

    output = args.output
    if output is None and not args.no_draw:
        base = os.path.splitext(args.video)[0]
        output = f"{base}__annotated.mp4"

    r = analyze(args.model, args.video, output, args.score, args.low,
                args.nms, (args.tsize, args.tsize), draw=not args.no_draw)
    print(json.dumps(r, indent=2))


if __name__ == "__main__":
    main()
