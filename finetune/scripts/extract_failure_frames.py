#!/usr/bin/env python3
"""Store Vision — fine-tuning step 1 (failure-focused frame extraction).

Random frames waste labeling effort. This script runs the CURRENT model over
your clips and pulls out the frames that show the three known failures, sorting
them into buckets so you label exactly what the model is getting wrong:

  false_positive/  frames where the model fires a store-implausible class
                   (dog, cat, knife, ...). Labeling these frames' REAL objects
                   and leaving the phantom unlabeled is how you suppress the FP.
  night_distant/   dark frames that contain weak/low-confidence or small (far)
                   person detections -> the "misses people past ~15ft at night"
                   case. These need the missed people HAND-labeled.
  boxes/           frames containing box-like objects (your inventory) so you
                   can draw box/packet.

A manifest.csv records why each frame was chosen. Diversity de-dup avoids
keeping 30 near-identical frames.

Usage:
    PYTHONPATH=agent/YOLOX python finetune/scripts/extract_failure_frames.py \
        --videos test_footage/night.mp4 test_footage/retail_store.mp4 \
        --model models/yolox_s.onnx \
        --out finetune/images_to_label
"""
import argparse
import csv
import os

import cv2
import numpy as np
import onnxruntime

from yolox.data.data_augment import preproc as preprocess
from yolox.data.datasets import COCO_CLASSES
from yolox.utils import demo_postprocess, multiclass_nms

# Classes that should essentially never appear in a store/forecourt. A detection
# of one of these is almost certainly a false positive worth training against.
DEFAULT_SPURIOUS = {
    "bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra",
    "giraffe", "teddy bear", "knife", "fork", "spoon", "bowl", "wine glass",
    "cup", "scissors", "banana", "apple", "sandwich", "cake",
}
BOX_LIKE = {"handbag", "backpack", "suitcase"}
PERSON_ID = COCO_CLASSES.index("person")


def infer(sess, in_name, frame, size, low_thr, nms_thr):
    img, ratio = preprocess(frame, size)
    out = sess.run(None, {in_name: img[None, :, :, :].astype(np.float32)})[0]
    p = demo_postprocess(out, size)[0]
    b, s = p[:, :4], p[:, 4:5] * p[:, 5:]
    xyxy = np.empty_like(b)
    xyxy[:, 0] = b[:, 0] - b[:, 2] / 2
    xyxy[:, 1] = b[:, 1] - b[:, 3] / 2
    xyxy[:, 2] = b[:, 0] + b[:, 2] / 2
    xyxy[:, 3] = b[:, 1] + b[:, 3] / 2
    xyxy /= ratio
    dets = multiclass_nms(xyxy, s, nms_thr=nms_thr, score_thr=low_thr)
    return dets if dets is not None else np.zeros((0, 6), np.float32)


def sig(frame, n=32):
    g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.resize(g, (n, n)).astype(np.float32)


def too_similar(s, kept, thresh):
    return any(np.abs(s - k).mean() < thresh for k in kept)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--videos", nargs="+", required=True)
    ap.add_argument("--model", default="models/yolox_s.onnx")
    ap.add_argument("--out", default="finetune/images_to_label")
    ap.add_argument("--score", type=float, default=0.30, help="working threshold")
    ap.add_argument("--low", type=float, default=0.10, help="weak-detection floor")
    ap.add_argument("--nms", type=float, default=0.45)
    ap.add_argument("--tsize", type=int, default=640)
    ap.add_argument("--stride", type=int, default=3, help="analyze every Nth frame")
    ap.add_argument("--night-brightness", type=float, default=70.0,
                    help="mean luma (0-255) below which a frame is 'night'")
    ap.add_argument("--small-person-frac", type=float, default=0.12,
                    help="person bbox height < this fraction of frame = 'far'")
    ap.add_argument("--cap-fp", type=int, default=80)
    ap.add_argument("--cap-night", type=int, default=150)
    ap.add_argument("--cap-boxes", type=int, default=120)
    ap.add_argument("--diff-thresh", type=float, default=6.0)
    args = ap.parse_args()

    size = (args.tsize, args.tsize)
    sess = onnxruntime.InferenceSession(args.model, providers=["CPUExecutionProvider"])
    in_name = sess.get_inputs()[0].name

    buckets = {"false_positive": args.cap_fp,
               "night_distant": args.cap_night,
               "boxes": args.cap_boxes}
    for b in buckets:
        os.makedirs(os.path.join(args.out, b), exist_ok=True)
    kept_sigs = {b: [] for b in buckets}
    counts = {b: 0 for b in buckets}
    scanned = 0
    rows = []

    for video in args.videos:
        cap = cv2.VideoCapture(video)
        if not cap.isOpened():
            print(f"!! cannot open {video}"); continue
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        vh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 1
        idx = -1
        vname = os.path.splitext(os.path.basename(video))[0]
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            idx += 1
            if idx % args.stride:
                continue
            scanned += 1
            brightness = float(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).mean())
            dets = infer(sess, in_name, frame, size, args.low, args.nms)
            conf, cls = dets[:, 4], dets[:, 5].astype(int)
            names = [COCO_CLASSES[c] for c in cls]

            strong = conf >= args.score
            spurious = sorted({names[i] for i in range(len(names))
                               if strong[i] and names[i] in DEFAULT_SPURIOUS})
            is_person = cls == PERSON_ID
            weak_person = int((is_person & (conf >= args.low) & (conf < args.score)).sum())
            heights = (dets[:, 3] - dets[:, 1]) / vh
            far_person = int((is_person & strong & (heights < args.small_person_frac)).sum())
            boxlike = int(sum(strong[i] and names[i] in BOX_LIKE for i in range(len(names))))

            # assign to the highest-priority failure bucket this frame matches
            bucket = None
            if spurious:
                bucket = "false_positive"
            elif brightness < args.night_brightness and (weak_person or far_person):
                bucket = "night_distant"
            elif boxlike:
                bucket = "boxes"
            if bucket is None or counts[bucket] >= buckets[bucket]:
                continue
            s = sig(frame)
            if too_similar(s, kept_sigs[bucket], args.diff_thresh):
                continue

            fn = f"{vname}_f{idx:06d}.jpg"
            cv2.imwrite(os.path.join(args.out, bucket, fn), frame)
            kept_sigs[bucket].append(s)
            counts[bucket] += 1
            rows.append({
                "file": os.path.join(bucket, fn), "video": vname, "frame": idx,
                "timestamp_s": round(idx / fps, 2), "bucket": bucket,
                "brightness": round(brightness, 1),
                "spurious_classes": ";".join(spurious),
                "weak_persons": weak_person, "far_persons": far_person,
                "boxlike": boxlike,
            })
        cap.release()

    man = os.path.join(args.out, "manifest.csv")
    with open(man, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["file", "video", "frame", "timestamp_s",
                           "bucket", "brightness", "spurious_classes",
                           "weak_persons", "far_persons", "boxlike"])
        w.writeheader(); w.writerows(rows)

    print(f"scanned {scanned} frames (stride {args.stride})")
    for b in buckets:
        print(f"  {b:14s}: {counts[b]:4d} frames  ->  {args.out}/{b}/")
    print(f"manifest -> {man}")


if __name__ == "__main__":
    main()
