# Labeling Guide — Store Vision fine-tuning

This guide fixes **three specific failures** in the current model:

| # | Failure | Why it happens | What labeling does |
|---|---|---|---|
| 1 | Fires **dog / cat / knife / bowl** in a store | Pretrained COCO model hallucinates 80 classes; store clutter/mannequins look vaguely like animals | Show it those exact frames with the phantom region left as **background** → it learns to stop firing there |
| 2 | **Misses people past ~15 ft at night** | Small, low-contrast people fall below the confidence threshold | **Hand-label the missed people** in dark frames → it learns to detect them |
| 3 | **Doesn't detect product boxes** | COCO has no `box`/`packet` class | Draw `box`/`packet` on your inventory → it learns your two new classes |

You train **one** model with **8 classes** (`finetune/classes.txt`): `person,
bicycle, car, motorcycle, bus, truck, box, packet`.

> **Important change from the old plan:** the old guide said "only hand-label
> box/packet; let the COCO model auto-label people." That auto-labeler keeps
> people only at confidence ≥ 0.45 — which is **exactly the distant night people
> it misses**. Using it would re-teach failure #2. So on **night/dark frames you
> must hand-label people yourself.** On bright daytime frames the auto-labeler is
> still a fine time-saver (see §5).

---

## 0. Get the frames to label

The extractor already sorted frames by which failure they show:

```bash
PYTHONPATH=agent/YOLOX python finetune/scripts/extract_failure_frames.py \
    --videos test_footage/night.mp4 test_footage/walking.mp4 test_footage/retail_store.mp4 \
    --model models/yolox_s.onnx --out finetune/images_to_label
```

Output folders (and a `manifest.csv` explaining every pick):

```
finetune/images_to_label/
  false_positive/   frames where a phantom class fired  (failure #1)
  night_distant/    dark frames with weak/small people   (failure #2)
  boxes/            frames with box-like inventory        (failure #3)
```

---

## 1. How many frames — the budget

Aim for **~300 frames total**, weighted toward the hardest, highest-value case
(night). Not random frames — these curated ones.

| Bucket | Frames to label | Priority | Why |
|---|--:|---|---|
| **night_distant** | **120–150** | ★★★ highest | Theft happens at night; this is the money case and the hardest for the model |
| **boxes** | **80–120** | ★★ | Your two brand-new classes need enough examples to learn from |
| **false_positive** | **40–60** | ★ | A little goes a long way — a few dozen suppression frames kill most FPs |

**The real target is instances, not frames:** aim for **≥150 labeled boxes per
class you care about** (`person`, `box`, `packet`). Night frames give lots of
`person`; make sure enough `boxes` frames contain *many* boxes, or add more.

> On the clip you've given me so far (`retail_store.mp4`, daytime) the extractor
> found **27 false-positive frames** (bowl ×8, dog ×8, cat ×4, teddy bear ×3,
> knife, elephant…) and **120 box frames**, but **0 night frames** — that bucket
> only fills once you send the night clip. **Please upload the night + walking
> clips** so I can extract their frames; night is the whole point.

---

## 2. What exactly to label — the rules that decide model quality

**Label every REAL object of these classes, in every chosen frame:**

- **person** — draw a tight box around *every* person, **including the tiny,
  blurry, dark, far-away ones the model currently misses.** If your eye can tell
  it's a person, label it. This is the entire fix for the night-distance miss.
- **box** — cardboard boxes / cartons (your inventory, delivery boxes).
- **packet** — bagged/wrapped/parcel items.
- **car / truck / bus / motorcycle / bicycle** — only if they appear and matter
  (forecourt/lot). Indoor store: usually none.

**Do NOT label the phantoms.** In a `false_positive/` frame the model drew a
"dog" or "knife" on a shelf or mannequin. **Leave that spot empty.** By handing
in a frame where every real object is boxed and the phantom is *not*, you teach
the model that region is background. That is precisely what suppresses it.

**The one rule you must not break:** in a false-positive frame you still have to
label the *real* people/boxes in it. An unlabeled real person teaches
"person = background" and makes failure #2 worse. So: **box all real objects,
ignore only the phantom.**

Good-box hygiene:
- **Tight** — hug the object, don't crop it off, don't leave a margin.
- **Consistent** — the same kind of item is always the same class.
- **Hard cases included** — occluded, blurry, edge-of-frame, stacked. Skipping
  them makes a model that fails on them.

---

## 3. The tool: Label Studio (local, private)

Your footage shows customers' faces — keep it on your machine. Label Studio is
free, open-source, local, and exports COCO (what YOLOX trains on).

```bash
pip install label-studio
label-studio start          # opens http://localhost:8080
```

1. **Create Project** → `store-vision`.
2. **Data Import** → drag in all three folders from `finetune/images_to_label/`.
3. **Labeling Setup** → template **"Object Detection with Bounding Boxes"**, then
   paste this label config (all 8 classes, hotkeys 1–8):

   ```xml
   <View>
     <Image name="image" value="$image"/>
     <RectangleLabels name="label" toName="image">
       <Label value="person"     hotkey="1" background="#FF5C4D"/>
       <Label value="box"        hotkey="2" background="#00CC66"/>
       <Label value="packet"     hotkey="3" background="#3399FF"/>
       <Label value="car"        hotkey="4" background="#FFB347"/>
       <Label value="truck"      hotkey="5" background="#B084FF"/>
       <Label value="bus"        hotkey="6" background="#FFD166"/>
       <Label value="motorcycle" hotkey="7" background="#06D6A0"/>
       <Label value="bicycle"    hotkey="8" background="#EF476F"/>
     </RectangleLabels>
   </View>
   ```
4. **Label**: press the class hotkey, drag a tight box, repeat. `Ctrl/Cmd+Enter`
   saves and advances.
5. **Export → COCO** → you get a `.zip` with a `result.json` + `images/`.

**CVAT** is the alternative (also free/local, nicer for very large jobs, steeper
setup). Either works — both export COCO, which is all the next step needs. For
~300 frames, Label Studio is the faster path.

---

## 4. Split & format — handled for you

Don't split manually. Drop your export at `finetune/label_export/` and tell me;
`prepare_dataset.py` converts + splits it into YOLOX's COCO layout:

```
finetune/dataset/
  annotations/instances_train2017.json
  annotations/instances_val2017.json
  train2017/   val2017/         # ~85% / 15% split
```

---

## 5. Optional speed-up for the DAYTIME box frames only

For bright `boxes/` frames, you may pre-fill person/vehicle boxes with the COCO
model and then just add box/packet by hand:

```bash
PYTHONPATH=agent/YOLOX python finetune/scripts/autolabel_coco.py \
    --images finetune/images_to_label/boxes \
    --classes finetune/classes.txt \
    --out finetune/label_export_auto/auto_person_vehicle.json --score 0.45
```

**Do not do this for `night_distant/` frames** — the auto-labeler misses the very
people you're trying to teach. Label those by hand.

---

## 6. Hand back to me

Once exported, put it in `finetune/label_export/` and say so. I'll:
1. `prepare_dataset.py` → build + split the COCO dataset.
2. Give you the ready **Colab notebook** (`colab_finetune.ipynb`) to fine-tune
   `yolox-s` on a free T4 GPU and export `models/yolox_s_finetuned.onnx`.
3. Run `compare_models.py` (old vs new) on these same clips so we can *measure*
   that the phantoms are gone, the boxes are found, and the night people are
   detected — before/after, on your footage.
