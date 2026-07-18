#!/usr/bin/env python3
"""Store Vision — Phase 1 ONNX inference helper.

Runs the exported YOLOX-S ONNX model with ONNX Runtime and prints the detected
objects with their confidence scores (the official demo only draws them onto the
image and prints nothing). Also saves an annotated image.

Requires the YOLOX repo root on PYTHONPATH, e.g.:
    PYTHONPATH=third_party/YOLOX python scripts/run_inference.py \
        --model models/yolox_s.onnx --image third_party/YOLOX/assets/dog.jpg
"""
import argparse
import os

import cv2
import numpy as np
import onnxruntime

from yolox.data.data_augment import preproc as preprocess
from yolox.data.datasets import COCO_CLASSES
from yolox.utils import demo_postprocess, multiclass_nms, vis

# The Phase 1 classes Store Vision keeps (see SPEC section 3).
VEHICLES = {"car", "truck", "bus", "motorcycle", "bicycle"}
INVENTORY = {"box"}  # generic "box"; packets need light fine-tuning later


def relevant(name: str) -> bool:
    return name == "person" or name in VEHICLES or name in INVENTORY


def main() -> None:
    ap = argparse.ArgumentParser(description="YOLOX ONNX inference (Phase 1)")
    ap.add_argument("--model", required=True)
    ap.add_argument("--image", required=True)
    ap.add_argument("--score", type=float, default=0.3)
    ap.add_argument("--input-shape", default="640,640")
    ap.add_argument("--output-dir", default="outputs")
    args = ap.parse_args()

    h, w = (int(x) for x in args.input_shape.split(","))
    input_shape = (h, w)

    origin = cv2.imread(args.image)
    if origin is None:
        raise SystemExit(f"could not read image: {args.image}")
    img, ratio = preprocess(origin, input_shape)

    session = onnxruntime.InferenceSession(
        args.model, providers=["CPUExecutionProvider"]
    )
    output = session.run(None, {session.get_inputs()[0].name: img[None, :, :, :]})[0]

    preds = demo_postprocess(output, input_shape)[0]
    boxes, scores = preds[:, :4], preds[:, 4:5] * preds[:, 5:]

    xyxy = np.ones_like(boxes)
    xyxy[:, 0] = boxes[:, 0] - boxes[:, 2] / 2.0
    xyxy[:, 1] = boxes[:, 1] - boxes[:, 3] / 2.0
    xyxy[:, 2] = boxes[:, 0] + boxes[:, 2] / 2.0
    xyxy[:, 3] = boxes[:, 1] + boxes[:, 3] / 2.0
    xyxy /= ratio

    dets = multiclass_nms(xyxy, scores, nms_thr=0.45, score_thr=args.score)

    print(f"\nDetections on {os.path.basename(args.image)} (score >= {args.score}):")
    print(f"  {'class':<14}{'confidence':<12}{'phase-1?':<10}box [x1,y1,x2,y2]")
    if dets is not None:
        final_boxes, final_scores, final_cls = dets[:, :4], dets[:, 4], dets[:, 5]
        for box, sc, cl in zip(final_boxes, final_scores, final_cls):
            name = COCO_CLASSES[int(cl)]
            tag = "yes" if relevant(name) else "-"
            x1, y1, x2, y2 = box
            print(f"  {name:<14}{sc:<12.4f}{tag:<10}[{x1:.0f},{y1:.0f},{x2:.0f},{y2:.0f}]")

        vis_img = vis(origin, final_boxes, final_scores, final_cls,
                      conf=args.score, class_names=COCO_CLASSES)
        os.makedirs(args.output_dir, exist_ok=True)
        out_path = os.path.join(args.output_dir, os.path.basename(args.image))
        cv2.imwrite(out_path, vis_img)
        print(f"\nAnnotated image saved to {out_path}")
    else:
        print("  (none)")


if __name__ == "__main__":
    main()
