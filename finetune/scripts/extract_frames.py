#!/usr/bin/env python3
"""Store Vision — fine-tuning step 1: extract diverse frames to label.

Pulls a target number of frames out of one or more videos, skipping
near-identical frames so you don't waste labeling effort on 30 copies of the
same static shot. Writes JPEGs to finetune/images_to_label/.

Usage:
    python finetune/scripts/extract_frames.py \
        --videos data/clip.mp4 \
        --target 250 \
        --out finetune/images_to_label

Tips:
  - More *variety* beats more frames. If you can, record short clips of your
    products from a few angles / lighting conditions and pass several --videos.
  - 200-300 labeled frames is the SPEC target for a light fine-tune.
"""
import argparse
import os

import cv2
import numpy as np


def frame_signature(frame, size=32):
    """Tiny grayscale thumbnail used to measure how different two frames are."""
    g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.resize(g, (size, size)).astype(np.float32)


def main() -> None:
    ap = argparse.ArgumentParser(description="Extract diverse frames for labeling")
    ap.add_argument("--videos", nargs="+", required=True, help="input video path(s)")
    ap.add_argument("--target", type=int, default=250, help="approx frames to keep")
    ap.add_argument("--out", default="finetune/images_to_label")
    ap.add_argument("--diff-thresh", type=float, default=8.0,
                    help="min mean pixel diff (0-255) vs last kept frame to accept a new one; "
                         "raise to keep fewer/more-distinct frames, lower to keep more")
    ap.add_argument("--min-gap", type=int, default=3,
                    help="minimum frames to skip between candidates")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)

    # Count total frames so we can spread the target across all videos.
    totals = []
    for v in args.videos:
        c = cv2.VideoCapture(v)
        totals.append(int(c.get(cv2.CAP_PROP_FRAME_COUNT)) or 0)
        c.release()
    grand = sum(totals) or 1

    kept = 0
    for v, n in zip(args.videos, totals):
        share = max(1, round(args.target * (n / grand)))
        stride = max(args.min_gap, n // max(1, share))
        cap = cv2.VideoCapture(v)
        tag = os.path.splitext(os.path.basename(v))[0]
        last_sig = None
        idx = 0
        taken_here = 0
        print(f"{v}: {n} frames, aiming for ~{share} (stride {stride})")
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if idx % stride == 0:
                sig = frame_signature(frame)
                if last_sig is None or float(np.mean(np.abs(sig - last_sig))) >= args.diff_thresh:
                    fn = os.path.join(args.out, f"{tag}_{idx:06d}.jpg")
                    cv2.imwrite(fn, frame)
                    last_sig = sig
                    kept += 1
                    taken_here += 1
            idx += 1
        cap.release()
        print(f"  -> kept {taken_here} frames from {tag}")

    print(f"\nTotal kept: {kept} frames in {args.out}/")
    print("Next: label them (see finetune/LABELING_GUIDE.md).")


if __name__ == "__main__":
    main()
