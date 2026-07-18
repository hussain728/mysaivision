#!/usr/bin/env python3
"""Store Vision — fine-tuning step 3: build the merged YOLOX dataset.

Combines two annotation sources into one COCO dataset for a single combined
model:
  1. --auto-json   : person/vehicle boxes from autolabel_coco.py
  2. --export-dir  : your hand-drawn box/packet labels (Label Studio COCO export)

Both are keyed by image file name, merged per image, re-mapped to the class order
in finetune/classes.txt, and split into YOLOX's layout:

    finetune/dataset/
      annotations/instances_train2017.json
      annotations/instances_val2017.json
      train2017/<images>
      val2017/<images>

Either source may be omitted (e.g. auto-only, or hand-only).

Usage:
    python finetune/scripts/prepare_dataset.py \
        --auto-json finetune/label_export_auto/auto_person_vehicle.json \
        --export-dir finetune/label_export \
        --images finetune/images_to_label finetune/images_vehicles \
        --classes finetune/classes.txt --val-frac 0.15
"""
import argparse
import json
import os
import random
import shutil
from collections import defaultdict


def load_classes(path):
    with open(path) as f:
        return [ln.strip() for ln in f
                if ln.strip() and not ln.strip().startswith("#")]


def find_coco_json(export_dir):
    for root, _, files in os.walk(export_dir):
        for f in files:
            if f.endswith(".json"):
                p = os.path.join(root, f)
                try:
                    d = json.load(open(p))
                except (json.JSONDecodeError, OSError):
                    continue
                if isinstance(d, dict) and "annotations" in d and "images" in d:
                    return d
    return None


def find_image(images_dirs, base):
    for d in images_dirs:
        cand = os.path.join(d, base)
        if os.path.exists(cand):
            return cand
    for d in images_dirs:
        for root, _, files in os.walk(d):
            if base in files:
                return os.path.join(root, base)
    return None


def index_source(coco, name_to_id):
    """Return {basename: {'wh':(w,h)|None, 'anns':[(cat_id,bbox),...]}} for a COCO dict."""
    if coco is None:
        return {}
    catid_to_name = {c["id"]: c["name"] for c in coco["categories"]}
    imgid_to_base = {im["id"]: os.path.basename(im["file_name"]) for im in coco["images"]}
    imgid_to_wh = {im["id"]: (im.get("width"), im.get("height")) for im in coco["images"]}
    out = {}
    for im in coco["images"]:
        b = os.path.basename(im["file_name"])
        out.setdefault(b, {"wh": imgid_to_wh[im["id"]], "anns": []})
    for a in coco["annotations"]:
        b = imgid_to_base[a["image_id"]]
        name = catid_to_name[a["category_id"]]
        if name not in name_to_id:
            continue  # class not in our list (e.g. hand export has an extra class)
        out.setdefault(b, {"wh": imgid_to_wh.get(a["image_id"]), "anns": []})
        out[b]["anns"].append((name_to_id[name], [float(x) for x in a["bbox"]]))
    return out


def main():
    ap = argparse.ArgumentParser(description="Merge auto + hand labels into YOLOX dataset")
    ap.add_argument("--auto-json", default=None, help="person/vehicle auto-labels")
    ap.add_argument("--export-dir", default=None, help="hand box/packet COCO export dir")
    ap.add_argument("--classes", default="finetune/classes.txt")
    ap.add_argument("--images", nargs="+",
                    default=["finetune/images_to_label", "finetune/images_vehicles"])
    ap.add_argument("--out", default="finetune/dataset")
    ap.add_argument("--val-frac", type=float, default=0.15)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    class_names = load_classes(args.classes)
    name_to_id = {n: i + 1 for i, n in enumerate(class_names)}
    print(f"classes ({len(class_names)}): {class_names}")

    auto = index_source(json.load(open(args.auto_json)) if args.auto_json else None, name_to_id)
    hand_coco = find_coco_json(args.export_dir) if args.export_dir else None
    if args.export_dir and hand_coco is None:
        raise SystemExit(f"no COCO json found under {args.export_dir}")
    hand = index_source(hand_coco, name_to_id)
    print(f"auto-label images: {len(auto)} | hand-label images: {len(hand)}")

    # union of all images, merged annotations
    all_bases = sorted(set(auto) | set(hand))
    merged = {}
    for b in all_bases:
        wh = (auto.get(b, {}).get("wh")) or (hand.get(b, {}).get("wh"))
        anns = list(auto.get(b, {}).get("anns", [])) + list(hand.get(b, {}).get("anns", []))
        if anns:  # skip images with no labels at all
            merged[b] = {"wh": wh, "anns": anns}
    print(f"merged: {len(merged)} labeled images")

    random.seed(args.seed)
    bases = list(merged)
    random.shuffle(bases)
    n_val = max(1, int(len(bases) * args.val_frac))
    splits = {"val2017": bases[:n_val], "train2017": bases[n_val:]}
    print(f"split -> train {len(splits['train2017'])}, val {len(splits['val2017'])}")

    categories = [{"id": i + 1, "name": n, "supercategory": ""}
                  for i, n in enumerate(class_names)]
    os.makedirs(os.path.join(args.out, "annotations"), exist_ok=True)
    per_class = defaultdict(int)
    id_to_name = {v: k for k, v in name_to_id.items()}

    for split, split_bases in splits.items():
        img_dir = os.path.join(args.out, split)
        os.makedirs(img_dir, exist_ok=True)
        images, annotations = [], []
        ann_id = 1
        for img_id, b in enumerate(split_bases):
            src = find_image(args.images, b)
            if src is None:
                print(f"  WARN image not found, skipping: {b}"); continue
            shutil.copy2(src, os.path.join(img_dir, b))
            wh = merged[b]["wh"]
            if not wh or wh[0] is None:
                import cv2
                im = cv2.imread(src); wh = (im.shape[1], im.shape[0])
            images.append({"id": img_id, "file_name": b,
                           "width": int(wh[0]), "height": int(wh[1])})
            for cat_id, bbox in merged[b]["anns"]:
                annotations.append({"id": ann_id, "image_id": img_id,
                                    "category_id": cat_id, "bbox": bbox,
                                    "area": bbox[2] * bbox[3], "iscrowd": 0})
                ann_id += 1
                per_class[id_to_name[cat_id]] += 1
        json.dump({"images": images, "annotations": annotations, "categories": categories},
                  open(os.path.join(args.out, "annotations", f"instances_{split}.json"), "w"))
        print(f"  {split}: {len(images)} imgs, {len(annotations)} boxes")

    print("\nboxes per class:")
    for n in class_names:
        flag = "  <-- few examples" if 0 < per_class[n] < 40 else (
               "  <-- NONE (won't be learned)" if per_class[n] == 0 else "")
        print(f"  {n:<12}{per_class[n]}{flag}")
    print(f"\ndataset ready at {args.out}/  (num_classes = {len(class_names)})")


if __name__ == "__main__":
    main()
