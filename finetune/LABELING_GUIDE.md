# Labeling Guide — Store Vision fine-tuning (step 1)

Goal: draw boxes around **your** products/packets (the things the pretrained
model misses) in ~200–300 frames, and export them in **COCO format**, which is
what YOLOX trains on. This guide is the labeling step only; Colab training and
ONNX re-export come after.

You already have **221 frames** extracted to `finetune/images_to_label/`
(from `data/clip.mp4`). Label those.

---

## 0. Before you click: decide your classes

Keep the class list **small and consistent** — a light fine-tune on ~250 frames
can't learn 30 fine-grained SKUs. Good starting points:

- Simplest / most robust: **`box`** and **`packet`** (2 classes).
- If specific products matter and look distinct: name them, e.g.
  `chips_bag`, `soda_bottle`, `cereal_box` — but budget ~80–150 boxes *per class*,
  so more classes = more labeling.

Write your final list, one per line, into `finetune/classes.txt`. The order
there defines the class **id** order used everywhere downstream (0-based).

> Distinguishing *which* exact product (SKU-level) is Phase 10 in the SPEC and
> needs far more data. For now, prefer coarse classes that you can label
> consistently.

---

## 1. Recommended tool: Label Studio (local, private)

Your footage shows customers' faces, so keep it on your machine. Label Studio is
free, open-source, runs locally, and exports COCO.

```bash
# in a separate venv or the project venv
pip install label-studio
label-studio start
```

It opens `http://localhost:8080` in your browser.

1. **Create Project** → name it `store-vision`.
2. **Data Import** → drag in everything from `finetune/images_to_label/`.
3. **Labeling Setup** → template **"Object Detection with Bounding Boxes"**.
   Replace the label list with your classes from `classes.txt`, e.g.:
   ```xml
   <View>
     <Image name="image" value="$image"/>
     <RectangleLabels name="label" toName="image">
       <Label value="box"    background="#00CC66"/>
       <Label value="packet" background="#3399FF"/>
     </RectangleLabels>
   </View>
   ```
4. **Label**: for each image, press the class hotkey (1, 2, …), drag a tight box
   around each instance. `Ctrl/Cmd+Enter` (or "Submit") saves and advances.
5. When done: **Export → COCO**. You get a `.zip` with `result.json` +
   an `images/` folder.

### Faster alternative: Roboflow (cloud)
`roboflow.com` free tier has a slicker UI, auto train/val split, and
augmentation, and exports "COCO" or "YOLOX" directly. Trade-off: your frames are
uploaded to their cloud. Fine for non-sensitive footage; avoid for anything with
identifiable customers unless you're comfortable with that.

---

## 2. How to draw good boxes (this decides model quality)

- **Tight**: box hugs the object, no big margin, no cropping it off.
- **Label every instance** of your classes in the frame — missed objects teach
  the model that those pixels are "background" and *hurt* it.
- **Include hard cases**: partially occluded, blurry, edge-of-frame, stacked
  boxes, different lighting. Skipping hard cases = a model that fails on them.
- **Be consistent**: same object type → always the same class. Inconsistent
  labels are worse than fewer labels.
- **Don't label** person/car/etc. **unless** we're building one combined model
  (see the question I'll ask you). If we run a separate inventory model, you only
  label your products here.
- Aim for a rough balance — if one class has 400 boxes and another has 15, the
  rare one won't learn. Extract/label more frames containing the rare one.

Target: **≥ ~150 labeled instances per class**, spread across the 200–300 frames.

---

## 3. Split train / validation

Hold out ~15–20% of images for validation so we can measure whether fine-tuning
actually helped. Label Studio export is one flat set; the dataset-prep script
(next step, `prepare_dataset.py`) will split it into YOLOX's expected layout:

```
finetune/dataset/
  annotations/
    instances_train2017.json
    instances_val2017.json
  train2017/   <- training images
  val2017/     <- validation images
```

---

## 4. Hand back to me

Once you've exported, drop the export (the `result.json` / `annotations.coco.json`
and images) somewhere in the repo — e.g. `finetune/label_export/` — and tell me.
I'll:
1. Run `prepare_dataset.py` to convert + split into the COCO layout above.
2. Give you a ready-to-run **Colab notebook** that fine-tunes `yolox-s` from the
   pretrained weights on your dataset (free T4 GPU).
3. Re-export the improved checkpoint to `models/yolox_s_finetuned.onnx` and
   re-run it on your clips so we can see the boxes it was missing.

You don't need a GPU locally — labeling is all CPU/browser. The GPU part is Colab.
