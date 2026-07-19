#!/usr/bin/env python3
"""Store Vision — fine-tuning step 4: compare OLD vs NEW model on the same clips.

Runs two ONNX models over identical footage and prints a before/after report
that directly measures the three fixes:

  * false positives  -> total store-implausible detections (should drop to ~0)
  * night/distance    -> person detections + avg person confidence (should rise)
  * product boxes     -> box/packet detections (0 with the old COCO model,
                         >0 once the fine-tuned model learns them)

Each model carries its own class-name list (the old COCO model has 80 classes;
the fine-tuned model has the 8 from finetune/classes.txt), so detections are
named correctly for each.

Usage:
    PYTHONPATH=agent/YOLOX python finetune/scripts/compare_models.py \
        --old models/yolox_s.onnx \
        --new models/yolox_s_finetuned.onnx --new-classes finetune/classes.txt \
        --videos test_footage/night.mp4 test_footage/retail_store.mp4
"""
import argparse
from collections import Counter

import cv2
import numpy as np
import onnxruntime

from yolox.data.data_augment import preproc as preprocess
from yolox.data.datasets import COCO_CLASSES
from yolox.utils import demo_postprocess, multiclass_nms

# Spurious = COCO classes implausible in a store/forecourt (the complement of a
# small "plausible" set). Catches night hallucinations like train/book/tv/chair.
PLAUSIBLE = {
    "person", "bicycle", "car", "motorcycle", "bus", "truck",
    "backpack", "handbag", "suitcase", "umbrella", "bottle",
}
SPURIOUS = set(COCO_CLASSES) - PLAUSIBLE


def load_classes(path):
    with open(path) as f:
        return [ln.strip() for ln in f
                if ln.strip() and not ln.strip().startswith("#")]


def run(model, classes, video, score, nms, size, stride):
    sess = onnxruntime.InferenceSession(model, providers=["CPUExecutionProvider"])
    in_name = sess.get_inputs()[0].name
    cap = cv2.VideoCapture(video)
    totals = Counter()
    person_confs = []
    small_person = 0
    vh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 1
    pid = classes.index("person") if "person" in classes else -1
    idx = -1
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        idx += 1
        if idx % stride:
            continue
        img, ratio = preprocess(frame, size)
        out = sess.run(None, {in_name: img[None, :, :, :].astype(np.float32)})[0]
        p = demo_postprocess(out, size)[0]
        b, s = p[:, :4], p[:, 4:5] * p[:, 5:]
        xyxy = np.empty_like(b)
        xyxy[:, 0] = b[:, 0] - b[:, 2] / 2; xyxy[:, 1] = b[:, 1] - b[:, 3] / 2
        xyxy[:, 2] = b[:, 0] + b[:, 2] / 2; xyxy[:, 3] = b[:, 1] + b[:, 3] / 2
        xyxy /= ratio
        dets = multiclass_nms(xyxy, s, nms_thr=nms, score_thr=score)
        if dets is None:
            continue
        for row in dets:
            c = int(row[5])
            name = classes[c] if c < len(classes) else f"cls{c}"
            totals[name] += 1
            if c == pid:
                person_confs.append(float(row[4]))
                if (row[3] - row[1]) / vh < 0.12:
                    small_person += 1
    cap.release()
    return {
        "totals": totals,
        "person": len(person_confs),
        "person_avg_conf": round(float(np.mean(person_confs)), 4) if person_confs else None,
        "far_person": small_person,
        "spurious": sum(v for k, v in totals.items() if k in SPURIOUS),
        "boxes": totals.get("box", 0) + totals.get("packet", 0),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", default="models/yolox_s.onnx")
    ap.add_argument("--old-classes", default=None, help="default: COCO-80")
    ap.add_argument("--new", required=True)
    ap.add_argument("--new-classes", default="finetune/classes.txt")
    ap.add_argument("--videos", nargs="+", required=True)
    ap.add_argument("--score", type=float, default=0.30)
    ap.add_argument("--nms", type=float, default=0.45)
    ap.add_argument("--tsize", type=int, default=640)
    ap.add_argument("--stride", type=int, default=2)
    args = ap.parse_args()

    size = (args.tsize, args.tsize)
    old_classes = load_classes(args.old_classes) if args.old_classes else list(COCO_CLASSES)
    new_classes = load_classes(args.new_classes)

    for v in args.videos:
        o = run(args.old, old_classes, v, args.score, args.nms, size, args.stride)
        n = run(args.new, new_classes, v, args.score, args.nms, size, args.stride)
        print(f"\n================  {v}  ================")
        print(f"{'metric':<26}{'OLD':>12}{'NEW':>12}{'change':>12}")

        def line(label, a, b, better_up=True, pct=False):
            if a is None or b is None:
                d = "n/a"
            elif pct:
                d = f"{(b-a)*100:+.1f}pp"
            else:
                d = f"{b-a:+d}" if isinstance(a, int) else f"{b-a:+.3f}"
            av = f"{a:.3f}" if isinstance(a, float) else str(a)
            bv = f"{b:.3f}" if isinstance(b, float) else str(b)
            print(f"{label:<26}{av:>12}{bv:>12}{d:>12}")

        line("person detections", o["person"], n["person"])
        line("person avg conf", o["person_avg_conf"], n["person_avg_conf"], pct=True)
        line("far/small persons", o["far_person"], n["far_person"])
        line("SPURIOUS (false pos)", o["spurious"], n["spurious"])
        line("box+packet detections", o["boxes"], n["boxes"])
        # show which spurious classes the old model produced
        sp = {k: v for k, v in o["totals"].items() if k in SPURIOUS}
        if sp:
            print("  old phantom classes:",
                  ", ".join(f"{k}={v}" for k, v in sorted(sp.items(), key=lambda x: -x[1])))


if __name__ == "__main__":
    main()
