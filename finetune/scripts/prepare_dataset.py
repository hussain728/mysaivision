#!/usr/bin/env python3
"""Store Vision — fine-tuning step 3: turn a label export into YOLOX's COCO layout.

Takes a COCO-format export (Label Studio "COCO" export, or Roboflow "COCO")
and produces the directory layout YOLOX trains on:

    finetune/dataset/
      annotations/instances_train2017.json
      annotations/instances_val2017.json
      train2017/<images>
      val2017/<images>

Categories are re-mapped to the order in finetune/classes.txt (id 1 = first
line, 2 = second, ...), so training is deterministic regardless of how the
labeling tool numbered them.

Usage:
    python finetune/scripts/prepare_dataset.py \
        --export-dir finetune/label_export \
        --classes finetune/classes.txt \
        --val-frac 0.15
"""
import argparse
import json
import os
import random
import shutil
from collections import defaultdict


def find_coco_json(export_dir):
    """Locate the COCO annotations JSON inside an export folder."""
    candidates = []
    for root, _, files in os.walk(export_dir):
        for f in files:
            if f.endswith(".json"):
                candidates.append(os.path.join(root, f))
    for p in candidates:
        try:
            with open(p) as fh:
                d = json.load(fh)
            if isinstance(d, dict) and "annotations" in d and "images" in d:
                return p, d
        except (json.JSONDecodeError, OSError):
            continue
    raise SystemExit(f"no COCO json (with images+annotations) found under {export_dir}")


def find_image(images_dirs, file_name):
    base = os.path.basename(file_name)
    for d in images_dirs:
        cand = os.path.join(d, base)
        if os.path.exists(cand):
            return cand
    # last resort: walk
    for d in images_dirs:
        for root, _, files in os.walk(d):
            if base in files:
                return os.path.join(root, base)
    return None


def main():
    ap = argparse.ArgumentParser(description="COCO export -> YOLOX dataset layout")
    ap.add_argument("--export-dir", default="finetune/label_export")
    ap.add_argument("--classes", default="finetune/classes.txt")
    ap.add_argument("--out", default="finetune/dataset")
    ap.add_argument("--val-frac", type=float, default=0.15)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    with open(args.classes) as f:
        class_names = [ln.strip() for ln in f
                       if ln.strip() and not ln.strip().startswith("#")]
    name_to_id = {n: i + 1 for i, n in enumerate(class_names)}  # COCO ids are 1-based
    print(f"classes ({len(class_names)}): {class_names}")

    coco_path, coco = find_coco_json(args.export_dir)
    print(f"using annotations: {coco_path}")

    # map the export's category ids -> our canonical ids via category NAME
    export_catid_to_name = {c["id"]: c["name"] for c in coco["categories"]}
    unknown = set(export_catid_to_name.values()) - set(name_to_id)
    if unknown:
        raise SystemExit(f"export has classes not in classes.txt: {sorted(unknown)}\n"
                         f"fix names in {args.classes} or in the labeling tool.")

    images_dirs = [args.export_dir, os.path.join(args.export_dir, "images")]

    imgs = coco["images"]
    anns_by_img = defaultdict(list)
    for a in coco["annotations"]:
        anns_by_img[a["image_id"]].append(a)

    random.seed(args.seed)
    random.shuffle(imgs)
    n_val = max(1, int(len(imgs) * args.val_frac))
    splits = {"val2017": imgs[:n_val], "train2017": imgs[n_val:]}
    print(f"{len(imgs)} images -> train {len(splits['train2017'])}, val {len(splits['val2017'])}")

    categories = [{"id": i + 1, "name": n, "supercategory": "inventory"}
                  for i, n in enumerate(class_names)]

    os.makedirs(os.path.join(args.out, "annotations"), exist_ok=True)
    total_ann = 0
    per_class = defaultdict(int)
    for split, split_imgs in splits.items():
        img_dir = os.path.join(args.out, split)
        os.makedirs(img_dir, exist_ok=True)
        out_images, out_anns = [], []
        ann_id = 1
        for im in split_imgs:
            src = find_image(images_dirs, im["file_name"])
            if src is None:
                print(f"  WARN: image not found, skipping: {im['file_name']}")
                continue
            base = os.path.basename(src)
            shutil.copy2(src, os.path.join(img_dir, base))
            im2 = dict(im); im2["file_name"] = base
            out_images.append(im2)
            for a in anns_by_img.get(im["id"], []):
                name = export_catid_to_name[a["category_id"]]
                a2 = dict(a)
                a2["category_id"] = name_to_id[name]
                a2["id"] = ann_id; ann_id += 1
                a2.setdefault("iscrowd", 0)
                # ensure area present (YOLOX/coco eval expects it)
                if "area" not in a2 and "bbox" in a2:
                    a2["area"] = float(a2["bbox"][2]) * float(a2["bbox"][3])
                out_anns.append(a2)
                per_class[name] += 1
                total_ann += 1
        out = {"images": out_images, "annotations": out_anns, "categories": categories}
        with open(os.path.join(args.out, "annotations", f"instances_{split}.json"), "w") as f:
            json.dump(out, f)
        print(f"  {split}: {len(out_images)} imgs, {len(out_anns)} boxes")

    print(f"\ntotal boxes: {total_ann}")
    for n in class_names:
        print(f"  {n:<12}{per_class[n]}")
    if any(per_class[n] < 50 for n in class_names):
        print("\nNOTE: some class has < 50 boxes — consider labeling more of it "
              "before training, or accept weaker accuracy on that class.")
    print(f"\ndataset ready at {args.out}/  (num_classes = {len(class_names)})")


if __name__ == "__main__":
    main()
