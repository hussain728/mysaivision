# Fine-tuning YOLOX on your products

The pretrained COCO model already handles person + vehicles, but it doesn't know
*your* packets/boxes. This folder is the light fine-tune the SPEC calls for
(~200–300 labeled frames, free Colab GPU), then a re-export to ONNX.

## The workflow

```
1. extract frames   ->  finetune/scripts/extract_frames.py    [DONE: 221 frames]
2. LABEL them        ->  finetune/LABELING_GUIDE.md            <-- YOU ARE HERE
3. prepare dataset   ->  finetune/scripts/prepare_dataset.py   [BUILT + tested]
4. fine-tune on Colab->  finetune/colab_finetune.ipynb         [BUILT] (free T4 GPU)
5. re-export to ONNX ->  models/yolox_s_finetuned.onnx         (notebook step 6)
6. verify on clips   ->  scripts/detect_video.py               (two-model runtime, built after)
```

Steps 3–4 are ready to run the moment your COCO export lands in
`finetune/label_export/`. The two-class exp is `finetune/exps/yolox_s_box_packet.py`.

## Baseline (before fine-tuning)

`outputs/store_inventory_baseline.mp4` shows what the current COCO model finds as
inventory on the store clip: only shopping **baskets/bags** (handbag 1325,
backpack 28, suitcase 6 detections) — the boxed/packaged products on the shelves
are **not** detected at all. That is the gap this fine-tune closes. Still:
`outputs/store_inventory_baseline_frame.jpg`.

## Layout

```
finetune/
├── classes.txt            # YOUR class names (edit this)
├── LABELING_GUIDE.md      # step 2, start here
├── colab_finetune.ipynb   # step 4: fine-tune on a free Colab GPU + export ONNX
├── exps/
│   └── yolox_s_box_packet.py   # YOLOX 2-class experiment (box, packet)
├── images_to_label/       # 221 extracted frames (git-ignored: privacy)
├── label_export/          # drop your Label Studio / Roboflow export here
├── dataset/               # COCO layout, filled by prepare_dataset.py
│   ├── annotations/
│   ├── train2017/
│   └── val2017/
└── scripts/
    ├── extract_frames.py
    └── prepare_dataset.py
```

## Scope note

This makes the model **see** your inventory. Turning detections into
**entry/exit counts** is separate line/zone-counting logic (SPEC Phase 3),
built on top of whatever the model detects — fine-tuning alone does not count.
