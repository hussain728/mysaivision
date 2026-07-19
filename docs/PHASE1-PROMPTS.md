# Phase 1 Prompts — Detection Core

**Goal:** YOLOX detecting person, vehicle, and box/packet — exported to ONNX —
running correctly on footage from your own camera.

**Time:** 1–3 days. **Gate to pass:** correct boxes on people and vehicles in *your*
footage, not just a demo image.

**How to use:** one prompt per message in Claude Code. Run it, **look at the output
yourself**, then move on. Do not paste prompt 2 before prompt 1 actually works.

The traps in these prompts are real — they were hit and solved in advance. Leave the
warnings in; they save hours.

---

## PROMPT 0 — Project setup

*Purpose: clean structure and a virtualenv so nothing pollutes your system Python,
and Claude Code knows where the docs live.*

```
I'm building an AI camera detection system. All specs are in /docs
(PRD.md, SPEC.md, TRD.md, FLOWS.md, SCHEMA.md, IMPLEMENTATION.md).

Read /docs/SPEC.md and /docs/IMPLEMENTATION.md first.

Set up the project skeleton only — no application code yet:
1. Folder structure: /agent, /docs, /models, /test_footage, /scripts
2. Python 3.12 virtual environment in /agent, activated for all
   future work
3. .gitignore BEFORE anything else — must exclude: .env*,
   config.yaml, *.pth, *.onnx, *.db, clips/, test_footage/,
   __pycache__/, venv/
4. git init and a first commit

Confirm the structure and that the venv is active.
```

**Check:** `.gitignore` exists and blocks secrets and model files. This matters — a
committed `config.yaml` with camera passwords is a real problem to undo later.

---

## PROMPT 1 — Install YOLOX and export to ONNX

*Purpose: get the model running. This is the step with the two traps that stop most
people cold.*

```
Implement Phase 1, step 1 from /docs/IMPLEMENTATION.md: get YOLOX
running and exported to ONNX. Nothing from later phases.

1. Clone https://github.com/Megvii-BaseDetection/YOLOX into /agent

2. CRITICAL — do NOT run YOLOX's requirements.txt. It tries to build
   onnx-simplifier, which fails without cmake and will block you.
   Install these individually instead:
     torch torchvision onnx onnxruntime opencv-python numpy
     loguru tqdm tabulate thop
   Then install the package itself with:
     pip install --no-deps -e .

3. Download the pretrained checkpoint:
   https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_s.pth

4. Verify it works BEFORE exporting — run the demo on the bundled
   test image:
     PYTHONPATH=. python3 tools/demo.py image -n yolox-s \
       -c yolox_s.pth --path assets/dog.jpg --conf 0.25 \
       --tsize 640 --save_result --device cpu
   NOTE: the PYTHONPATH=. prefix is required. Without it you get
   "No module named 'yolox'".

5. Export to ONNX using tools/export_onnx.py, model name yolox-s,
   output /models/yolox_s.onnx. Skip the onnx-simplifier step
   (use --no-onnxsim if available) to avoid the build failure above.

Show me the annotated demo image with detected objects and their
confidence scores, and confirm the ONNX file exists.
```

**Check:** you should see boxes on the test image — a dog, a bicycle, and a truck.
The truck matters: that's your "vehicle" class working. Person detection uses the
same model.

**If it fails:** paste the *entire* error back to Claude Code. Don't debug by hand.

---

## PROMPT 2 — Clean detection script (ONNX runtime)

*Purpose: your own reusable script instead of YOLOX's demo — this becomes the core
of the agent.*

```
Now write our own detection module at /agent/detector.py. This is
code we keep and build the agent on, so make it clean.

Requirements:
- Load /models/yolox_s.onnx with onnxruntime
- Use CUDAExecutionProvider if a GPU is available, else CPU.
  Log clearly at startup which one is in use (TRD §2).
- Reuse YOLOX's ONNX preprocessing and postprocessing (letterbox
  resize to 640, decode outputs, NMS) so detections are correct —
  do not invent your own.
- Keep ONLY these classes (see /docs/SPEC.md §3.1):
  person, car, truck, bus, motorcycle, bicycle, handbag, backpack,
  suitcase
  NOTE: COCO has NO box or packet class. Do not try to filter for
  one. Theft/loss detection needs only person + vehicle and works
  fully on the pretrained model. Box/packet detection requires
  fine-tuning (SPEC §3.2) and is a later pass.
- Expose: detect(frame) -> list of {class, confidence, bbox}
- Add bottom_center(bbox) — the "where a person stands" anchor we'll
  need for zones in Phase 3
- A CLI mode that runs on a video file, draws labeled boxes, saves an
  annotated output video, and prints per-frame inference time plus a
  total count per class

Test it on assets/dog.jpg first to confirm results match the demo.
```

**Check:** results should match Prompt 1's output. If your own script finds fewer or
different objects, the pre/postprocessing is wrong — fix it now, because every later
phase depends on this being right.

---

## PROMPT 3 — Run on your real footage (the actual gate)

*Purpose: the only test that counts. Demo images prove nothing about your cameras.*

**First, record 2–3 clips yourself:** 2–5 minutes each, from your home camera —
one in daylight, one at night, one with a person walking at a realistic distance.
Save them to `/test_footage/`.

```
Run detector.py on my real camera clips in /test_footage/ (I've added
day, night, and walking clips).

For each clip report:
- total detections per class
- average confidence for person detections
- average inference time per frame
- any frames where a person is clearly visible but NOT detected

Save the annotated videos so I can watch them. Then summarize:
where is detection weakest — distance, lighting, camera angle?
```

**Check — this IS Gate 1.** Watch the annotated videos yourself. Ask:
- Are people boxed reliably as they move through the frame?
- Does it hold up at night / in glare / at distance?
- Any constant false detections (a mannequin, a poster, a shadow read as a person)?

**Pass → go to Phase 2.** **Fail → Prompt 4.**

---

## PROMPT 4 — Fine-tune (ONLY if Prompt 3 failed)

*Purpose: adapt the model to your specific conditions. Skip entirely if detection is
already good — and it often is for people and vehicles.*

```
Detection is unreliable in my footage: [describe exactly — e.g.
"misses people beyond ~15 feet at night", "doesn't detect my
product boxes at all"].

Set up a fine-tuning workflow:
1. A script to extract frames from my clips at intervals, focusing
   on the failure cases above
2. Recommend a free labeling tool (Label Studio or CVAT) and
   generate the correct export format for YOLOX
3. A Google Colab notebook (free GPU) that fine-tunes yolox-s on my
   labeled data and exports the result to ONNX
4. An evaluation script comparing old vs new model on the same clips

Walk me through the labeling step first — how many frames, and what
exactly to label.
```

**Reality check:** expect 200–300 labeled frames per problem class, and a few days of
tedious work.

**Important distinction:** people and vehicles almost always work well out of the box
— if they do, **pass Gate 1 and move to Phase 2 now.** Boxes and packets are NOT in
COCO and always require fine-tuning, but that is an *inventory* feature, not a theft
feature. Do not block your theft/loss build waiting on it. Come back and fine-tune
for inventory after Phase 4 alerts are working.

---

## Phase 1 checklist

- [ ] Project structure, venv, `.gitignore` protecting secrets
- [ ] YOLOX installed (deps individually, `--no-deps -e .`)
- [ ] Demo runs with `PYTHONPATH=.`
- [ ] Exported to `/models/yolox_s.onnx`
- [ ] `detector.py` works, logs GPU/CPU, filters to our classes
- [ ] `bottom_center()` implemented (Phase 3 needs it)
- [ ] **Runs on YOUR footage with reliable person + vehicle detection**
- [ ] Inference time recorded — you'll compare against it in Phase 2's benchmark
- [ ] Committed to git

**When all boxes are ticked, you've passed Gate 1.** Move to Phase 2: live RTSP
ingestion.
