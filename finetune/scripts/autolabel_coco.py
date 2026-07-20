#!/usr/bin/env python3
"""Store Vision — fine-tuning step 2b: auto-label person + vehicles.

For a single combined model we still only hand-label box/packet. Person and
vehicle boxes are generated automatically by the existing COCO model
(models/yolox_s.onnx) and written as a COCO-format JSON. prepare_dataset.py then
merges these auto-labels with your hand-drawn box/packet labels.

The category ids match finetune/classes.txt (1-based). Only classes that appear
in BOTH classes.txt AND the COCO model's vocabulary are emitted here (i.e.
person + vehicles); box/packet are left for you to draw.

Usage:
    python finetune/scripts/autolabel_coco.py \
        --images finetune/images_to_label finetune/images_vehicles \
        --model models/yolox_s.onnx \
        --classes finetune/classes.txt \
        --out finetune/label_export_auto/auto_person_vehicle.json \
        --score 0.45
"""
import argparse
import glob
import json
import os

import cv2
import numpy as np
import onnxruntime

from yolox.data.data_augment import preproc as preprocess
from yolox.data.datasets import COCO_CLASSES
from yolox.utils import demo_postprocess, multiclass_nms

# COCO classes we auto-label from (the pretrained model is reliable on these),
# and how they map onto OUR class names. handbag/backpack/suitcase collapse to
# the single 'bag' class. A mapped name is only kept if it's in classes.txt, so
# dropping e.g. bicycle from classes.txt automatically stops labeling it.
COCO_REMAP = {"handbag": "bag", "backpack": "bag", "suitcase": "bag"}
AUTOLABEL_COCO = {"person", "car", "truck", "motorcycle", "bus", "bicycle",
                  "handbag", "backpack", "suitcase"}


def build_session(model_path):
    so = onnxruntime.SessionOptions()
    so.intra_op_num_threads = os.cpu_count() or 4
    return onnxruntime.InferenceSession(model_path, sess_options=so,
                                        providers=["CPUExecutionProvider"])


def detect(session, frame, input_shape, score_thr, nms_thr):
    img, ratio = preprocess(frame, input_shape)
    out = session.run(None, {session.get_inputs()[0].name: img[None, :, :, :]})[0]
    preds = demo_postprocess(out, input_shape)[0]
    boxes, scores = preds[:, :4], preds[:, 4:5] * preds[:, 5:]
    xyxy = np.ones_like(boxes)
    xyxy[:, 0] = boxes[:, 0] - boxes[:, 2] / 2.0
    xyxy[:, 1] = boxes[:, 1] - boxes[:, 3] / 2.0
    xyxy[:, 2] = boxes[:, 0] + boxes[:, 2] / 2.0
    xyxy[:, 3] = boxes[:, 1] + boxes[:, 3] / 2.0
    xyxy /= ratio
    dets = multiclass_nms(xyxy, scores, nms_thr=nms_thr, score_thr=score_thr)
    if dets is None:
        return []
    return dets  # rows: x1,y1,x2,y2,score,cls


def main():
    ap = argparse.ArgumentParser(description="Auto-label person/vehicle with the COCO model")
    ap.add_argument("--images", nargs="+", required=True, help="image dir(s)")
    ap.add_argument("--model", default="models/yolox_s.onnx")
    ap.add_argument("--classes", default="finetune/classes.txt")
    ap.add_argument("--out", default="finetune/label_export_auto/auto_person_vehicle.json")
    ap.add_argument("--score", type=float, default=0.45,
                    help="keep only confident auto-labels (clean > complete)")
    ap.add_argument("--nms", type=float, default=0.45)
    ap.add_argument("--input-shape", default="640,640")
    args = ap.parse_args()

    h, w = (int(x) for x in args.input_shape.split(","))
    input_shape = (h, w)

    with open(args.classes) as f:
        class_names = [ln.strip() for ln in f
                       if ln.strip() and not ln.strip().startswith("#")]
    name_to_id = {n: i + 1 for i, n in enumerate(class_names)}
    # COCO names we'll read, whose mapped target exists in classes.txt
    source = {c for c in AUTOLABEL_COCO
              if COCO_REMAP.get(c, c) in name_to_id}
    print(f"auto-labeling COCO classes: {sorted(source)} "
          f"-> targets {sorted({COCO_REMAP.get(c, c) for c in source})}")

    session = build_session(args.model)

    paths = []
    for d in args.images:
        paths += sorted(glob.glob(os.path.join(d, "*.jpg")))
        paths += sorted(glob.glob(os.path.join(d, "*.png")))
    print(f"{len(paths)} images")

    images, annotations = [], []
    ann_id = 1
    per_class = {COCO_REMAP.get(c, c): 0 for c in source}
    for img_id, p in enumerate(paths):
        frame = cv2.imread(p)
        if frame is None:
            print(f"  WARN unreadable: {p}"); continue
        H, W = frame.shape[:2]
        images.append({"id": img_id, "file_name": os.path.basename(p),
                       "width": W, "height": H})
        for x1, y1, x2, y2, score, cls in detect(session, frame, input_shape,
                                                  args.score, args.nms):
            coco_name = COCO_CLASSES[int(cls)]
            if coco_name not in source:
                continue
            name = COCO_REMAP.get(coco_name, coco_name)  # e.g. handbag -> bag
            bw, bh = float(x2 - x1), float(y2 - y1)
            annotations.append({
                "id": ann_id, "image_id": img_id,
                "category_id": name_to_id[name],
                "bbox": [float(x1), float(y1), bw, bh],
                "area": bw * bh, "iscrowd": 0,
                "score": float(score),  # provenance; ignored by training
            })
            ann_id += 1
            per_class[name] += 1

    categories = [{"id": i + 1, "name": n, "supercategory": ""}
                  for i, n in enumerate(class_names)]
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        json.dump({"images": images, "annotations": annotations,
                   "categories": categories}, f)

    print(f"\nwrote {args.out}: {len(images)} images, {len(annotations)} auto boxes")
    for n in sorted(per_class):          # keyed by OUR class names (e.g. 'bag')
        print(f"  {n:<12}{per_class[n]}")
    print("box/packet are NOT auto-labeled — you draw those by hand.")


if __name__ == "__main__":
    main()
