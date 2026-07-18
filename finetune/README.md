# Fine-tuning YOLOX on your products

The pretrained COCO model already handles person + vehicles, but it doesn't know
*your* packets/boxes. This folder is the light fine-tune the SPEC calls for
(~200–300 labeled frames, free Colab GPU), then a re-export to ONNX.

## The workflow

```
1. extract frames   ->  finetune/scripts/extract_frames.py   [DONE: 221 frames]
2. LABEL them        ->  finetune/LABELING_GUIDE.md            <-- YOU ARE HERE
3. prepare dataset   ->  finetune/scripts/prepare_dataset.py   (after labeling)
4. fine-tune on Colab->  finetune/colab_finetune.ipynb         (free T4 GPU)
5. re-export to ONNX ->  models/yolox_s_finetuned.onnx
6. verify on clips   ->  scripts/detect_video.py with the new model
```

Steps 3–6 are scaffolded once your labels come back — the exact dataset paths
and `num_classes` depend on your class list (`finetune/classes.txt`).

## Layout

```
finetune/
├── classes.txt            # YOUR class names (edit this)
├── LABELING_GUIDE.md      # step 2, start here
├── images_to_label/       # 221 extracted frames (git-ignored: privacy)
├── label_export/          # drop your Label Studio / Roboflow export here
├── dataset/               # COCO layout, filled by prepare_dataset.py
│   ├── annotations/
│   ├── train2017/
│   └── val2017/
└── scripts/
    └── extract_frames.py
```

## Scope note

This makes the model **see** your inventory. Turning detections into
**entry/exit counts** is separate line/zone-counting logic (SPEC Phase 3),
built on top of whatever the model detects — fine-tuning alone does not count.
