# Implementation Plan — [PRODUCT NAME TBD]

The execution doc. `PRD` = why, `SPEC` = what, `TRD` = engineering contract,
`FLOWS` = sequences, `DESIGN` = look, `SCHEMA` = data. **This one = what you do,
in what order, and when you're allowed to move on.**

Assumes: you build with Claude Code, testing on your home camera until Phase 8.
Full-time ≈ 10 weeks. Part-time ≈ 16–20. **Do not compress by skipping gates.**

---

## DAY 0 — Unblock and set up (do this first, today)

- [ ] **Regain camera access** — Dahua H5A @ `192.168.100.134`. DMSS → Forgot
      Password, or physical reset button (~10–15s). *This blocks everything.*
- [ ] Set the device password to **letters and numbers only** (`@ # : /` break RTSP)
- [ ] Confirm in VLC:
      `rtsp://admin:PASS@192.168.100.134:554/cam/realmonitor?channel=1&subtype=1`
      **If VLC won't play it, no code will either. Fix it here.**
- [ ] Install Python 3.12, Git, Node.js, VS Code, Claude Code
- [ ] `git init` a repo; create `/docs` and drop in all 7 documents
- [ ] Create free accounts: Supabase, Vercel, Clerk, Stripe (test mode), Firebase
- [ ] Add MCP servers to Claude Code: Supabase, Vercel, Stripe, Clerk
- [ ] Create `.gitignore` **before** the first commit — `.env*`, `config.yaml`,
      `*.pth`, `*.onnx`, `clips/`, `*.db`

**Gate:** VLC plays your camera. Claude Code runs. Nothing secret is in git.

---

## PHASE 1 — Detection core · Week 1

**Build:** YOLOX → ONNX, detecting person / vehicle / box on video files.
**Docs:** SPEC §3, TRD §2.

Known traps (already solved for you):
- Do **not** run YOLOX's `requirements.txt` — `onnx-simplifier` fails without cmake.
  Install deps individually, then `pip install --no-deps -e .`
- YOLOX scripts need the repo root on `PYTHONPATH` or imports fail

Steps: clone YOLOX → install deps → download `yolox_s.pth` → export to ONNX → run on
`assets/dog.jpg` → **then run on a real clip from your camera**.

**GATE 1:** correct boxes on people and vehicles in *your own* footage.
If accuracy is poor in your lighting/angles, label ~200–300 frames and fine-tune on
Colab free GPU **now** — not later. Everything downstream inherits this quality.

---

## PHASE 2 — Live ingestion · Week 2

**Build:** RTSP streams, threading, ONVIF discovery, benchmark.
**Docs:** SPEC §2c, TRD §2 & §5.

1. `config.yaml` with a cameras list
2. One reader thread per camera keeping **only the newest frame** (sequential reads
   fall behind and analyze stale footage)
3. Round-robin sampling, `sample_interval_seconds` default 2
4. Auto-reconnect with backoff 1s→60s, forever; one camera dying never stops others
5. **ONVIF auto-discovery** — scan network, list devices, fetch stream URIs
6. **Benchmark mode** — 60s run, reports per-frame time, effective FPS, CPU, and a
   plain verdict: "this PC can handle N cameras"

**GATE 2:** runs continuously; **unplug the camera mid-run and it reconnects without
crashing**; benchmark reports honestly. This gate decides whether your US sites need
GPUs — a real budget answer, from data.

---

## PHASE 3 — Zones, lines, counting · Week 3

**Build:** point-in-polygon, counting.  **Docs:** SPEC §5, §4b/4c.

Zones (polygon + type), lines (2 points + direction), `bottom_center()` as the person
anchor, zone counts and line-crossing counts. Write a small tool to draw zones on a
captured frame and save the coordinates — you'll use it constantly.

**GATE 3:** stand inside your drawn zone → it registers. Step out → it stops. Counts
are stable, not flickering ±3 every frame.

---

## PHASE 4 — Theft alerts (THE MILESTONE) · Week 4

**Build:** schedule, alert rules, cooldown, SQLite, FCM push, clip buffer.
**Docs:** SPEC §6, FLOWS B2/B3, TRD §3.

1. `schedules` — open hours in **local time**
2. `should_alert()` — restricted = any time; monitored = closed hours only
3. **Cooldown 5 min per (camera, zone)** — without this you get 50 alerts per event
4. SQLite (WAL mode); log *every* detection, alert on only some
5. Snapshot: annotated JPEG ≤1280px, <200KB
6. FCM push + **email fallback** (an undelivered theft alert is a product failure)
7. Rolling 120s local clip buffer per camera; cut [-15s,+15s] on alert, **store
   locally, upload nothing**

**GATE 4 — the one that matters:** set your "closed hours" to now, walk into the
zone, and **your phone buzzes with a snapshot in under 10 seconds.**

🎉 You now have a working product. Everything after this is scale and business.

---

## PHASE 5 — Announcements · Week 5 (short)

Auto-alerts already exist from Phase 4. Add the staff message board (plain table +
UI later) and low-count alerts for `count` zones. **Docs:** SPEC §4d.

---

## PHASE 6 — Cloud spine · Weeks 5–6

**Build:** Supabase + Vercel + sync.  **Docs:** SCHEMA §1–4, §11; FLOWS B4.

1. Supabase project; **run SCHEMA.md as versioned migrations** (never hand-edit in UI)
2. Partitions for `events`/`counts`; a job to create next month's partition
3. Vercel API routes: `POST /events`, `POST /counts`, `GET /limits`
4. Agent sync thread: batches of 100, mark `synced=1` on 200, backfill after outages
5. **Idempotency:** `unique (site_id, agent_event_id)` — retries must not duplicate
6. Snapshot upload to Supabase Storage
7. Heartbeat every 60s → `sites.last_seen` + health metrics

**GATE 6:** pull the internet for 30 minutes. Detection and alerts continue. Reconnect
→ every queued event backfills, **zero duplicates**.

---

## PHASE 7 — Auth, dashboard, reports · Weeks 7–8

**Build:** Clerk, Next.js dashboard, RLS, reports.
**Docs:** SCHEMA §2 & §10, DESIGN §4, FLOWS A4.

1. Clerk auth + organizations; `app_users` / `memberships` / `membership_sites`
2. **RLS on every table** + `visible_site_ids()`. Owners: all. Managers/clerks:
   assigned sites. Clerks get read policies and **no write policies at all.**
3. Dashboard per DESIGN §4: sites overview (+ Night Ribbon), event feed, event detail,
   reports, announcements, search, settings
4. `daily_rollup` materialized view; reports read the rollup, never raw events
5. Clip-on-demand via `agent_commands` queue (FLOWS B6)
6. **"Real / False alarm" button on every event** — this is your data pipeline, not a
   nice-to-have
7. Incident cases: create case, attach events, add notes

**GATE 7:** log in as a test *clerk* and confirm you cannot see another site or write
anything. Test cross-tenant reads directly against the API — they must fail.

---

## PHASE 7b — Trial, licensing, billing · Week 9

**Build:** the money layer.  **Docs:** SPEC §7 & §7b, TRD §6.

1. `POST /trial/start` + global `trial_registry` (**reinstall ≠ new trial**)
2. License keys, activation, device fingerprint binding, deactivate action
3. **Encrypt the ONNX model**; key derived from signed token + fingerprint; decrypt
   **in memory only**. No license → no model → no detection. *This is your real
   anti-piracy measure; the rest is supporting.*
4. Signed tokens (Ed25519), agent verifies with embedded public key
5. State machine: `trial → active → grace (3d) → suspended`; anti-rollback on clock
6. Stripe: products, Checkout, webhooks (`checkout.session.completed`,
   `invoice.payment_succeeded/failed`, `subscription.deleted`)
7. **Renewal extends the SAME key** — never issue a new one
8. Tier limits enforced **server-side AND agent-side**
9. Website: `/`, `/pricing`, `/download`, `/buy`, `/renew`, `/docs`, `/support`
   per DESIGN §3 — **published prices, "Download free trial" as the CTA**

**GATE 7b:** expire a license → 3 days pass (fake the clock) → **cameras stop** →
pay in Stripe test mode → **cameras resume automatically with no human action.**
Then repeat the whole test with the machine offline.

---

## PHASE 8 — Package, deploy, tune · Week 10+

**Build:** installer, then your first real site.  **Docs:** TRD §8, DESIGN §5.

1. PyInstaller one-file, obfuscated, **code-signed** (also kills SmartScreen warnings)
2. Windows Service: auto-start on boot, auto-restart on failure
3. Installer wizard: key → system check → ONVIF scan → credentials → zones → hours →
   **mandatory test alert the user must confirm receiving**
4. Auto-update with one-version rollback
5. Diagnostics bundle export (logs + redacted config) — one click, saves you hours
6. **Remote-install on ONE of your US sites** (RustDesk/AnyDesk)
7. Run 14 days. Tune thresholds, cooldowns, zone shapes.

**GATE 8 — the release gate:** **false positives under 1 per site per week, sustained
14 days.** Do not sell to anyone until this holds. A system owners learn to mute is
worth less than no system, and in a tight-knit community that story travels.

---

## PHASE 9 — Scale your own sites · Weeks 12–16

Roll to 5–6 sites, then all 17. Every week: review flagged events, add hard cases to
your labeled test set, retrain when accuracy is worth it.

**Track from day one:** incidents caught, estimated loss prevented, hours of footage
review saved. **This becomes your ROI number — the single asset that unlocks sales
and your raise.**

**GATE 9:** ≥5 sites live for 30+ days with a documented dollar figure.

---

## Working with Claude Code — the method

1. **One phase per session.** Start: *"Read /docs/SPEC.md and /docs/TRD.md. Implement
   Phase N only. Do not build anything from later phases."*
2. **One step per prompt.** Never "build the whole agent." Small, testable increments.
3. **Paste full errors back.** Don't debug by hand — that's what the tool is for.
4. **Commit after every working step.** Cheap rollback beats careful editing.
5. **Point it at the right doc:** data → SCHEMA, performance/security → TRD,
   sequences → FLOWS, UI → DESIGN.
6. **After each phase:** *"Review this phase against TRD §5 (failure behavior) and
   list anything unhandled."*

## Do NOT build during Weeks 1–10

Gesture-based shoplifting AI · SKU/product recognition · native mobile apps ·
SMS/Twilio · reseller portal · Docker packaging · exotic NPU support · paid ads.
Every one of these is a way to end week 10 with no working system.

## The three rules

1. **Never pass a gate you haven't actually tested.** Gates exist because the failure
   modes here are silent — bad detection, duplicate events, wrong-timezone alerts.
2. **Phase 4 before everything.** Your riskiest assumption is "will an owner trust
   these alerts." Answer it in week 4, not week 10.
3. **Your first spend is data, not features.** A reliable detector on 5 sites beats a
   feature-rich one that cries wolf.

**Next action:** reset that camera password. Everything above waits on it.
