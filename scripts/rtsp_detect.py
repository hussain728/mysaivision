#!/usr/bin/env python3
"""Store Vision — connect to an IP camera (RTSP) and run detection.

A Phase-2 preview: prove a real camera works end to end. Opens an RTSP stream
(Dahua/Avigilon H5A/any ONVIF camera), samples one frame every N seconds (as the
agent loop will), runs the YOLOX ONNX detector, and saves annotated snapshots
(and optionally a short clip).

Works with the COCO model (default classes) or a fine-tuned model
(--class-names-file). Accepts a file path in place of --rtsp for offline testing.

DH-H5A / Dahua RTSP URL:
    rtsp://<user>:<pass>@<ip>:554/cam/realmonitor?channel=1&subtype=0   # main stream
    rtsp://<user>:<pass>@<ip>:554/cam/realmonitor?channel=1&subtype=1   # sub stream (use this)
Avigilon H5A (ONVIF) usually exposes the URL via ONVIF; a common direct form:
    rtsp://<user>:<pass>@<ip>:554/defaultPrimary?streamType=u

Example:
    PYTHONPATH=third_party/YOLOX python scripts/rtsp_detect.py \
        --rtsp "rtsp://admin:pass@192.168.1.108:554/cam/realmonitor?channel=1&subtype=1" \
        --model models/yolox_s.onnx --sample-seconds 2 --max-snapshots 10
"""
import argparse
import importlib.util
import os
import time

import cv2

# reuse the exact YOLOX pipeline from detect_video.py
_spec = importlib.util.spec_from_file_location(
    "detect_video", os.path.join(os.path.dirname(__file__), "detect_video.py"))
dv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dv)

from yolox.data.datasets import COCO_CLASSES  # noqa: E402
from yolox.utils import vis  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="RTSP camera detection (Phase 2 preview)")
    ap.add_argument("--rtsp", required=True,
                    help="RTSP URL (or a local video path for offline testing)")
    ap.add_argument("--model", default="models/yolox_s.onnx")
    ap.add_argument("--class-names-file", default=None,
                    help="class names for a fine-tuned model (defaults to COCO)")
    ap.add_argument("--score", type=float, default=0.35)
    ap.add_argument("--nms", type=float, default=0.45)
    ap.add_argument("--input-shape", default="640,640")
    ap.add_argument("--sample-seconds", type=float, default=2.0,
                    help="grab one frame every N seconds (matches the agent loop)")
    ap.add_argument("--max-snapshots", type=int, default=10,
                    help="stop after this many annotated snapshots (0 = run until interrupted)")
    ap.add_argument("--out-dir", default="outputs/rtsp")
    args = ap.parse_args()

    h, w = (int(x) for x in args.input_shape.split(","))
    input_shape = (h, w)

    if args.class_names_file:
        with open(args.class_names_file) as f:
            class_names = [ln.strip() for ln in f
                           if ln.strip() and not ln.strip().startswith("#")]
        keep_ids = set(range(len(class_names)))
    else:
        class_names = list(COCO_CLASSES)
        keep_ids = dv.KEEP_IDS  # person / vehicle / box-like

    session = dv.build_session(args.model)
    os.makedirs(args.out_dir, exist_ok=True)

    # OpenCV over TCP is more reliable than UDP for RTSP
    os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")
    cap = cv2.VideoCapture(args.rtsp, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        raise SystemExit(
            f"could not open stream: {args.rtsp}\n"
            "checks: camera IP reachable? RTSP enabled? user/pass correct? "
            "try the sub-stream (subtype=1) and confirm port 554 is open.")

    src_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    every = max(1, int(round(src_fps * args.sample_seconds)))
    print(f"connected: {args.rtsp}")
    print(f"stream ~{src_fps:.0f} fps -> sampling 1 frame every {args.sample_seconds}s "
          f"(~every {every} frames)\n")

    idx = snaps = 0
    last_fail = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            last_fail += 1
            if last_fail > 50:
                print("stream ended / dropped; stopping.")
                break
            time.sleep(0.05)
            continue
        last_fail = 0
        idx += 1
        if idx % every:
            continue

        boxes, scores, cls = dv.detect(session, frame, input_shape,
                                       args.score, args.nms, keep_ids)
        ts = time.strftime("%Y%m%d_%H%M%S")
        if boxes is not None:
            summary = ", ".join(f"{class_names[int(c)]}:{s:.2f}"
                                for c, s in zip(cls, scores))
            frame = vis(frame, boxes, scores, cls, conf=args.score,
                        class_names=class_names)
        else:
            summary = "no detections"
        out = os.path.join(args.out_dir, f"snap_{ts}_{snaps:03d}.jpg")
        cv2.imwrite(out, frame)
        snaps += 1
        print(f"[{ts}] {out}  ->  {summary}")

        if args.max_snapshots and snaps >= args.max_snapshots:
            break

    cap.release()
    print(f"\nsaved {snaps} snapshots to {args.out_dir}/")


if __name__ == "__main__":
    main()
