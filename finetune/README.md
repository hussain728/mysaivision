# Fine-tuning YOLOX — one combined model

Trains a **single** YOLOX-S model that detects all 8 Store Vision classes:
`person, bicycle, car, motorcycle, bus, truck, box, packet`.

You hand-label **only box + packet**. Person + vehicle boxes are auto-labeled by
the existing COCO model and merged in, so you never draw a person or a car.

## The workflow

```
1. extract frames    -> finetune/scripts/extract_frames.py    [DONE]
     store frames  -> finetune/images_to_label/  (221, for box/packet + person)
     vehicle frames-> finetune/images_vehicles/  (188 from gas clip, for vehicles)
2a. LABEL box/packet -> finetune/LABELING_GUIDE.md             <-- YOU ARE HERE
2b. AUTO-label       -> finetune/scripts/autolabel_coco.py     [DONE]
     person+vehicle boxes from the COCO model -> label_export_auto/*.json
3. prepare dataset   -> finetune/scripts/prepare_dataset.py    [BUILT + tested]
     merges auto (person/vehicle) + hand (box/packet) into one 8-class dataset
4. fine-tune on Colab-> finetune/colab_finetune.ipynb          [BUILT] (free T4)
5. re-export to ONNX -> models/yolox_s_finetuned.onnx          (notebook step 6)
6. verify on clips   -> scripts/detect_video.py --model ... --class-names-file classes.txt
```

Steps 3–4 are ready to run the moment your box/packet COCO export lands in
`finetune/label_export/`. The 8-class exp is `finetune/exps/yolox_s_store.py`.

## Data reality check (important)

Auto-labels from your current footage give plenty of **person** and **car**, but
the other vehicle classes are sparse or absent:

| class   | auto-labeled boxes | note |
|---------|-------------------:|------|
| person  | ~2100              | strong |
| car     | ~160               | ok |
| truck   | ~8                 | weak |
| bus     | ~3                 | weak |
| motorcycle | ~3              | weak |
| bicycle | 0                  | **none in footage — won't be learned** |

So the combined model will be solid on **person + car + box + packet**, and weak
on the rare vehicles. To make those strong, add footage that contains them (a
lot/street clip) and re-run `extract_frames.py` + `autolabel_coco.py` before
training. Or, if you only ever need reliable *all-vehicle* detection, the
pretrained COCO model already does that perfectly out of the box.

## Baseline (before fine-tuning)

`outputs/store_inventory_baseline.mp4` shows what the current COCO model finds as
inventory on the store clip: only shopping **baskets/bags** (handbag 1325,
backpack 28, suitcase 6) — the boxed/packaged products on the shelves are **not**
detected. That is the gap this fine-tune closes.

## Layout

```
finetune/
├── classes.txt              # 8 class names (order = class id)
├── LABELING_GUIDE.md        # step 2a, start here
├── colab_finetune.ipynb     # step 4: fine-tune on a free Colab GPU + export ONNX
├── exps/
│   └── yolox_s_store.py     # YOLOX 8-class experiment
├── images_to_label/         # 221 store frames (git-ignored: privacy)
├── images_vehicles/         # 188 vehicle frames (git-ignored)
├── label_export/            # drop your Label Studio box/packet export here
├── label_export_auto/       # auto person/vehicle labels (git-ignored, regenerable)
├── dataset/                 # merged COCO layout, filled by prepare_dataset.py
└── scripts/
    ├── extract_frames.py
    ├── autolabel_coco.py
    └── prepare_dataset.py
```

## Scope note

This makes the model **see** your inventory + people + vehicles. Turning
detections into **entry/exit counts** is separate line/zone-counting logic
(SPEC Phase 3), built on top of whatever the model detects — fine-tuning alone
does not count.
