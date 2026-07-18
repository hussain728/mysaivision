# Store Vision — Build Specification (v2, full detection platform)

AI camera-vision system that turns existing store cameras into a full store
manager: theft/loss alerts, inventory counting, people & vehicle analytics,
announcements, and daily reports. Works with existing cameras, any hardware,
offline-first.

**Build priority: theft/loss works FIRST, then the rest layers on the same
detection engine.** Almost all detection here comes from ONE model (YOLOX) —
person, vehicle, box, and packet are the same model with different classes kept.
Counting, reports, and announcements are software on top of that engine.

Scoped to 8 phases for self-deployment across 17 owned locations (5-6 cameras
each), then productization. Two hard AI problems are deferred to phases 9-10 —
see the end.

---

## 1. Architecture

Three parts:

1. **Edge Agent** (Python) — runs on a PC at each location. Reads cameras, runs
   detection, applies rules, counts objects, fires alerts, logs locally, syncs up.
   Keeps working with no internet.
2. **Cloud API** (FastAPI + PostgreSQL) — receives events/counts from all agents,
   validates licenses, serves dashboard, stores announcements.
3. **Dashboard** (React) — all sites in one place: alerts, counts, reports,
   announcements board, search.

Data flow:
`cameras -> agent (detect + count + rules) -> local SQLite + phone alert -> sync -> cloud -> dashboard`

---

## 2. Tech Stack (do not substitute)

- Detection model: **YOLOX** (Apache-2.0, commercial-safe). Export to **ONNX**,
  run with **ONNX Runtime** for portability across any chip.
- Agent: **Python 3.12**, video via **OpenCV** (RTSP/ONVIF).
- Local store: **SQLite**. Cloud DB: **PostgreSQL**. Cloud API: **FastAPI**.
- Alerts: **Firebase Cloud Messaging (FCM)** push (free). SMS deferred.
- Dashboard: **React** (Vite). Auth: **Clerk** or **Supabase Auth**.
- Billing (later): **Stripe**.

Do NOT use Ultralytics YOLO — AGPL license would force open-sourcing the product.

---

## 3. Detection — What The Model Detects

One YOLOX model, keep these COCO classes:
- **person**
- **vehicles**: car, truck, bus, motorcycle, bicycle
- **inventory objects**: box, and packet-like items. NOTE: generic "box" works
  from the pretrained model; YOUR specific packets/products may need light
  fine-tuning on ~200-300 labeled photos (done free on Google Colab). Start with
  pretrained, fine-tune only where it misses.

Everything below is built on top of these detections.

---

## 4. Core Capabilities (all from the one engine)

### 4a. Theft / loss (FIRST priority)
Zone + schedule rules on person/vehicle detections -> phone alerts. Sections 6-8.

### 4b. Inventory counting
Count objects (boxes/packets) inside a defined zone or crossing a line.
- **Zone count**: how many boxes currently visible in the "stockroom shelf" zone.
- **Line count**: count items crossing a line at a receiving door (deliveries in).
Store counts over time -> feeds daily reports ("boxes received today").

### 4c. People & vehicle analytics
Count people entering zones (foot traffic, peak hours) and vehicles in lot zones.
Same counting mechanism as inventory, different class.

### 4d. Announcements (BOTH types)
- **Automatic alerts**: rule-triggered push (theft, low count, unknown after-hours).
- **Staff message board**: staff post text messages visible on the dashboard to
  all sites or one site. Pure software, no AI.

### 4e. Daily reports
Database queries over logged events/counts. Examples: boxes received today, peak
customer hours, cars in lot, theft alerts this week. Generated per site and
across all sites.

---

## 5. Zones, Lines, and Schedule

**Zone** (per camera): `name`, `type` (`restricted` / `monitored` / `count`),
`polygon` (list of `[x,y]` points). `count` zones are for inventory/people counts.

**Line** (per camera): `name`, two points defining a counting line, and a
direction. Used for receiving-door item counts and entrance people counts.

**Schedule** (per site): open hours per weekday. "Closed" = outside open window.

---

## 6. Alert Rules (theft/loss heart)

```
should_alert(zone, detection, now):
    if detection.class == "person":
        if zone.type == "restricted": return True          # any time
        if zone.type == "monitored":  return is_closed_hours(now)
    if detection.class in VEHICLES and zone.type == "restricted":
        return is_closed_hours(now)                          # dock/lot after hours
    return False
```

**Cooldown/debounce (critical):** after an alert for a `(camera, zone)` pair,
suppress further alerts for that pair for `cooldown_minutes` (default 5). Events
are still logged during cooldown; only the push is suppressed. One person in a
zone = one alert, not fifty.

**Low-count alert (inventory):** if a `count` zone's object count drops below a
configurable threshold, optionally fire a "low stock" announcement.

---

## 7. License Logic (offline-tolerant)

```
validate_license():
    try: token = POST cloud /license/validate {site_key}; cache with expiry
    except no_internet: token = read_cached_token()
    if token missing or expired: stop detection, show "reconnect to renew"
    else: continue
```

Agent runs on cached token while offline; reconnecting refreshes it. Only stops
if it cannot reach the server for LONGER than the token validity. This grace
period balances offline-first against subscription enforcement.

---

## 8. Sync Logic (offline-first)

```
sync_thread(): every 30s:
    if internet: batch = unsynced events/counts (limit 100)
                 POST cloud /events; on success mark synced
```

Events and counts accumulate locally when offline and catch up when connection
returns. Never block detection on sync.

---

## 9. Agent Main Loop

```
load config; validate_license(); open camera streams
loop:
  for each camera (round-robin, one frame every sample_interval_seconds=2):
      frame = grab_latest_frame(camera)
      dets  = filter_relevant(yolox_detect(frame))   # person, vehicle, box/packet
      # counting
      for zone in camera.count_zones: update_count(zone, dets)
      for line in camera.lines:       update_line_count(line, dets)
      # theft/loss + zone events
      for det in dets:
          anchor = bottom_center(det.bbox)
          for zone in camera.zones:
              if point_in_polygon(anchor, zone.polygon):
                  log_event_local(make_event(camera, zone, det))
                  if should_alert(zone, det, now) and not in_cooldown(camera,zone):
                      send_push_alert(event, draw_and_save(frame, det))
                      set_cooldown(camera, zone)
  sleep(sample_interval_seconds)
# background threads: sync_thread(), license_refresh()
```

`point_in_polygon` = standard ray-casting test.

---

## 10. Data Models

### Local (SQLite)
```
events(id, ts, camera_id, zone_id, object_class, confidence, snapshot_path, synced)
counts(id, ts, camera_id, zone_or_line_id, object_class, count, synced)
zones(id, camera_id, name, type, polygon)         -- polygon/points as JSON
lines(id, camera_id, name, points, direction)
```
Config (cameras, schedule, site_key, FCM key) in `config.yaml`.

### Cloud (PostgreSQL)
```
customers(id, name, tier, stripe_customer_id)
sites(id, customer_id, name, agent_key, location, last_seen)
cameras(id, site_id, name)
zones(id, camera_id, name, type, polygon)
lines(id, camera_id, name, points, direction)
events(id, site_id, camera_id, zone_id, ts, object_class, confidence, snapshot_url)
counts(id, site_id, camera_id, zone_or_line_id, ts, object_class, count)
announcements(id, customer_id, site_id_or_null, author, text, ts)
licenses(site_id, token, expires_at)
users(id, customer_id, email, ...)                -- via auth provider
```

---

## 11. Cloud API — Endpoints

- `POST /events` — batch of events from an agent (auth: agent_key).
- `POST /counts` — batch of counts from an agent.
- `POST /license/validate` — body `{site_key}` -> `{token, expires_at}`.
- `GET /sites` — sites + online/offline status.
- `GET /events` — filters: site, camera, zone, from, to, class.
- `GET /counts` — filters: site, camera, from, to, class (feeds reports).
- `GET /reports/daily` — computed daily summary per site / all sites.
- `GET /announcements` / `POST /announcements` — staff message board.

Auth: agents use per-site `agent_key`; dashboard users via Clerk/Supabase.

---

## 12. Dashboard — Screens

1. **Sites overview** — every site, online/offline, last sync, today's alerts + counts.
2. **Event feed** — filterable alerts with snapshot thumbnails.
3. **Event detail** — full snapshot + metadata.
4. **Reports** — daily/weekly: boxes received, peak hours, cars, theft alerts.
5. **Announcements board** — post/read staff messages (all sites or one).
6. **Search** — "everyone in {zone} between {time A} and {time B}."

Tables and thumbnails first; charts on the reports screen once data flows.

---

## 13. Build Order — 8 Phases (build and TEST each before the next)

Do everything up to Phase 8 on your OWN home camera. It is free and instant.

1. **Multi-object detection core** — YOLOX (ONNX) detecting person, vehicle, and
   box/packet on a video clip. Prove on real footage. Fine-tune only if it misses.
2. **Live camera ingestion** — read 5-6 RTSP streams, round-robin sampling.
3. **Zones + lines + counting** — point-in-polygon zones, counting lines, and
   count logic (boxes, people, cars). This unlocks inventory + analytics.
4. **Theft/loss rules + logging** — schedule, alert rules, cooldown, SQLite.
   THEFT ALERTS GO LIVE HERE (your first priority, working).
5. **Announcements** — automatic push alerts (FCM) + staff message board.
6. **Cloud spine** — FastAPI + PostgreSQL, /events + /counts + /license, sync,
   offline-tolerant license grace period.
7. **Daily reports + dashboard** — reports from logged counts/events; full
   dashboard (sites, feed, reports, announcements, search); auth (Clerk/Supabase).
8. **Real deployment + tuning** — remote-install agent on ONE USA site, connect
   its cameras, set zones/hours, run several days, KILL FALSE POSITIVES.

After Phase 8: roll to 4-5 more of the 17 sites, log dollars saved, then raise.

---

## 14. Deferred to phases 9-10 (do NOT attempt in the 8 phases)

- **Phase 9 — Gesture-based shoplifting detection** (spotting item concealment).
  A different, hard AI problem needing a custom-trained model. Veesion's moat.
  Build only after the core platform is proven and earning.
- **Phase 10 — SKU / product-level recognition** (identifying WHICH product, not
  just "a box"). Needs custom training per product. "Count objects" is Phase 3;
  "identify exact products" waits.

Also later: Stripe billing + subscription tiers, self-serve installer, SMS/voice
alerts, multi-tenant onboarding polish, exotic NPU chip support.

Keep the 8 phases focused. Cramming phases 9-10 into them is what breaks timelines.
