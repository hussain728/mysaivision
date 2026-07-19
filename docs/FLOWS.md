# Application & Software Flows — [PRODUCT NAME TBD]

Companion to `PRD.md` (why/what), `SPEC.md` (features), `TRD.md` (engineering
contract). This document defines **sequences**: what happens, in what order, and
what each component does at each step.

---

# PART A — APP FLOW (what the customer experiences)

## A1. End-to-end customer journey

```
  DISCOVER          website / LinkedIn / referral
     |
  DOWNLOAD          /download  → signed installer (.exe)
     |
  INSTALL           run installer → service registered → auto-start
     |
  ONBOARD           license screen → ONVIF scan → cameras → zones → hours
     |
  TRIAL (7 days)    full detection, 1 site / 2 cameras
     |
  ├── buys ────►  BUY → key emailed → paste → ACTIVE ──► renews ──► ACTIVE...
  |                                                   └─ doesn't ──► SUSPENDED
  └── doesn't ──►  TRIAL ENDED → detection stops → blocking screen
```

## A2. First-run onboarding (the make-or-break screen)

Target: **under 10 minutes, non-technical user, no phone call.**

```
1  WELCOME          "Turn your existing cameras into theft alerts"
2  LICENSE          [ Start 7-day free trial ]  [ I have a key ]
                    → trial: POST /trial/start (needs internet once)
3  SYSTEM CHECK     benchmark host → "This PC can handle up to N cameras"
                    ⚠ under-spec → warn, allow continue with fewer cameras
4  FIND CAMERAS     ONVIF network scan (auto) → list found devices
                    └ nothing found? → [ Enter RTSP URL manually ] fallback
5  CREDENTIALS      one username/password → test each stream → ✓ / ✗ per camera
                    → auto-select SUB-STREAM for detection
6  NAME CAMERAS     "Front Door", "Register", "Stockroom", "Pumps"
7  DRAW ZONES       live frame per camera → draw polygon → name → type:
                    restricted (alert any time) / monitored (alert when closed)
                    / count (inventory + traffic)
                    → offer smart defaults so a user can skip this
8  SET HOURS        open/close per weekday  → defines "after hours"
9  ALERTS           enter email → install PWA / enable push → SEND TEST ALERT
                    ✅ user must SEE one alert land before onboarding completes
10 DONE             "Monitoring 4 cameras at Main Street"
```

**Rule:** step 9 is mandatory. An owner who has felt one alert arrive trusts the
product. One who hasn't will ignore the first real one.

## A3. Daily use (what the owner actually does)

```
MORNING     push: "Daily report ready" → 1 screen: alerts, counts, peak hours
DURING DAY  nothing. Silence is the product working.
ALERT       phone buzzes → snapshot + zone + time
            → tap → event detail → [ Get clip ] → 15s before/after
            → [ Mark: real / false alarm ]        ← feeds tuning + your test set
WEEKLY      dashboard: compare sites, review flagged events, search
```

**"Mark false alarm" is not a nice-to-have.** It is how you gather the labeled data
that drives your false-positive gate and your only real moat.

## A4. Dashboard navigation

```
LOGIN (Clerk)
  └── SITES OVERVIEW  ← home. every site: online/offline, today's alerts, counts
        ├── SITE DETAIL     cameras, zones, hours, license status, agent health
        ├── EVENT FEED      filter: site/camera/zone/type/date → EVENT DETAIL
        │     └── EVENT DETAIL  snapshot, metadata, [Get clip], [Real/False]
        ├── REPORTS         daily/weekly: alerts, items received, peak hours
        ├── ANNOUNCEMENTS   auto-alert history + staff message board
        ├── SEARCH          "everyone in {zone} between {A} and {B}"
        └── SETTINGS
              ├── Billing        tier, usage vs limits, Stripe portal
              ├── License        key, state, expiry, device, [Deactivate device]
              ├── Users          invite, roles
              └── Notifications  which zones, which hours, per user
```

## A5. License states — what the customer sees

| State | App | Dashboard |
|---|---|---|
| `trial` | banner "Trial ends in N days" | countdown + [Buy] |
| `active` | normal, no interruption | green badge + expiry date |
| `grace` | daily warning "Cameras stop in N days" | amber badge + [Renew] |
| `suspended` | **blocking screen, detection off** | red badge + [Renew] |
| `revoked` | blocking screen | red, contact support |

---

# PART B — SOFTWARE FLOW (what the code does)

## B1. Agent startup sequence

```
START (service, on boot)
 │
 ├─1 load config.yaml + local SQLite (WAL mode)
 ├─2 CHECK LICENSE ──────────────────────────────┐
 │     online?  POST /license/validate           │
 │     offline? read cached signed token         │
 │     verify signature with embedded public key │
 │     anti-rollback: reject clock moved backward│
 │     state = trial | active | grace → continue │
 │     state = suspended | revoked   → B7        │
 ├─3 DERIVE MODEL KEY from token + fingerprint   │
 │     decrypt ONNX model INTO MEMORY only       │
 │     ✗ no valid token → no model → cannot run ─┘
 ├─4 init ONNX Runtime (CUDA if present, else CPU) — log which
 ├─5 apply tier limits → open at most max_cameras streams
 ├─6 start ONE reader thread per camera (keeps newest frame only)
 ├─7 start background threads: sync, license_refresh, heartbeat, clip_buffer
 └─8 enter MAIN LOOP (B2)
```

## B2. Main detection loop

```
LOOP forever:
  for each enabled camera (round-robin):
      frame = grab_latest_frame(cam)        # newest only; never a stale queue
      if frame is None: mark_unhealthy(cam); continue

      dets = yolox_detect(frame)            # ONNX
      dets = keep(person, vehicle, box/packet)

      # counting
      for zone in cam.count_zones: update_count(zone, dets)
      for line in cam.lines:       update_line_count(line, dets)

      # zone events + theft rules
      for det in dets:
          anchor = bottom_center(det.bbox)   # where a person "stands"
          for zone in cam.zones:
              if point_in_polygon(anchor, zone.polygon):
                  log_event_local(...)                    # ALWAYS log
                  if should_alert(zone, det, now)
                     and not in_cooldown(cam, zone):      # ← anti-spam
                        → ALERT PIPELINE (B3)
                        set_cooldown(cam, zone)           # default 5 min

  sleep(sample_interval_seconds)             # default 2s
```

## B3. Alert pipeline (event → phone in < 10s)

```
TRIGGER
  ├─ annotate frame → JPEG ≤1280px, q80 (<200 KB)      → save locally
  ├─ write event row to SQLite (synced=0)
  ├─ cut clip [-15s, +15s] from rolling buffer → local disk (DO NOT upload)
  ├─ queue push notification  ─────────────► FCM → phone/PWA
  │     no push token or delivery fails → EMAIL FALLBACK (required)
  └─ queue snapshot upload    ─────────────► Supabase Storage (when online)

Never blocks the detection loop. All I/O is queued.
```

## B4. Sync flow (offline-first)

```
every 30s:
  if no internet → do nothing (events keep accumulating locally)
  else:
     batch = SELECT * FROM events WHERE synced=0 LIMIT 100
     upload snapshots → Storage
     POST /events (batch) → on 200: UPDATE synced=1
     repeat until drained (backfills after any outage)
     same for counts
```

Detection **never** waits on sync. A week offline = a week of queued events that
backfill automatically on reconnect.

## B5. License lifecycle (runtime)

```
every 30 min:
  resp = POST /license/validate {key, fingerprint}   (or cached token if offline)

  active  and now < expires_at        → run normally
  past expiry, < 3 days (paid)        → run + daily warning push
  past expiry, ≥ 3 days               → SUSPEND (B7)
  trial expired (no grace)            → SUSPEND (B7)
  revoked                             → SUSPEND immediately
```

```
STRIPE                    CLOUD                        AGENT
payment succeeded ──► webhook → state=active ──► next poll → active
                                extend expires_at        → reopen cameras
                                                         → RESUME automatically
payment failed ────► webhook → expiry clock starts ──► grace → suspended
```

## B6. Clip retrieval (on demand)

```
per camera, always running: rolling 120s sub-stream buffer on local disk
                            (capped ~20GB total, oldest deleted first)

user taps [Get clip]
   → cloud writes a fetch command for that site
   → agent's next heartbeat (≤60s) picks it up
   → uploads the stored clip → Storage
   → cloud returns signed URL (≤15 min) → plays in dashboard
   → agent offline? → "clip available when site reconnects"
```

## B7. Suspended state

```
SUSPENDED:
   close ALL camera streams
   halt detection, unload model from memory
   show blocking renew screen
   poll /license/validate every 30 min  ← the ONLY thing that runs
   on active → restart from B1 step 3 (re-derive key, reopen cameras)
```

## B8. Failure & recovery

| Event | Flow |
|---|---|
| Camera drops | reader thread reconnects, backoff 1s→60s, forever. Others unaffected. |
| Camera down >15 min | mark offline **+ alert owner — a disabled camera is a security event** |
| Internet drops | detect + alert locally, queue events, resume sync on reconnect |
| Cloud 5xx | exponential backoff, keep queueing, never crash |
| Disk full | stop writing clips, keep detecting, dashboard warning |
| Model load fails | retry 3×, then exit non-zero → service manager restarts |
| Crash / power loss | service auto-restarts on boot; SQLite WAL = no data loss |
| Clock moved back | treat as tampering → suspend |

## B9. Data flow summary

```
CAMERA ──RTSP sub-stream──► AGENT
                              ├─ ONNX detection (LOCAL — video never leaves site)
                              ├─ zone/schedule rules
                              ├─ SQLite (events, counts, queue)
                              ├─ rolling clip buffer (local disk)
                              └─ sync ──► SUPABASE (events, counts, snapshots)
                                            │
                                            ├─► VERCEL dashboard (Clerk auth, RLS)
                                            └─► FCM ──► phone / PWA

STRIPE ──webhooks──► EDGE FUNCTION ──► licenses table ──► agent poll
```

**The privacy line that is also a sales line:** raw video never leaves the store
except one explicitly requested clip. Detection happens on the owner's own PC.
No facial recognition, ever.
