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
2. **Cloud** (Vercel + Supabase) — API routes receive events/counts from agents,
   Edge Functions validate licenses and handle Stripe webhooks, Postgres stores
   everything, Storage holds snapshots.
3. **Dashboard** (Next.js on Vercel, Clerk auth) — all sites in one place: alerts,
   counts, reports, announcements board, search, billing.

Data flow:
`cameras -> agent (detect + count + rules) -> local SQLite + phone alert -> sync -> cloud -> dashboard`

---

## 2. Tech Stack (do not substitute)

**Edge Agent**
- Detection model: **YOLOX** (Apache-2.0, commercial-safe). Export to **ONNX**,
  run with **ONNX Runtime** (GPU auto-detect, CPU fallback).
- **Python 3.12**, video via **OpenCV** (RTSP/ONVIF). Local store: **SQLite**.
- Push alerts: **Firebase Cloud Messaging (FCM)** (free). SMS deferred.

**Cloud (serverless — no VM to manage)**
- **Supabase** — PostgreSQL database + storage (snapshots) + row-level security.
- **Vercel** — hosts the dashboard AND the API (Next.js API routes / serverless
  functions). Replaces the earlier FastAPI-on-a-VM plan.
- **Supabase Edge Functions** — license validation + Stripe webhooks (server-side
  secrets never touch the client).
- **Clerk** — user authentication, organizations, and user management.
- **Stripe** — subscriptions, tiers, billing portal.

**Dashboard**
- **Next.js** (React) on Vercel. Clerk for login. Supabase client for data.

Do NOT use Ultralytics YOLO — AGPL would force open-sourcing the product.

### Why this stack (verdict)
Supabase + Vercel removes all server maintenance and has free tiers that cover
your own 17 sites. Clerk handles auth so you never write security-critical login
code yourself. All four have official MCP servers (Section 2b) so Claude Code can
work with them directly.

**One honest note:** Supabase includes its own auth, so Clerk overlaps with it.
Clerk is the better product for organizations/multi-tenant B2B, so using Clerk for
auth + Supabase for data is a valid and common combination — just be clear that
**Clerk owns identity, Supabase owns data.** Never build a second login path.

---

## 2b. MCP Servers for Claude Code

Add these MCP servers so Claude Code can read your schema, deploy, and inspect
billing directly instead of guessing:

| MCP | What it gives Claude Code |
|---|---|
| **Supabase** | Read/modify DB schema, run migrations, query tables |
| **Vercel** | Deploy, read build logs, manage env vars and domains |
| **Stripe** | Create products/prices, inspect subscriptions, test webhooks |
| **Clerk** | Inspect users/orgs, configure auth settings |

Install them via Claude Code's MCP configuration (`claude mcp add ...`) using each
vendor's official MCP server. Check current install commands in each vendor's docs
plus https://docs.claude.com/en/docs/claude-code — they change.

**Security rule:** give MCP servers scoped/read-mostly keys where possible, and
NEVER put production Stripe secret keys or Supabase service-role keys in a config
that gets committed to git. Use `.env.local` and a `.gitignore`.

## 2c. Camera Compatibility (all categories)

The agent is **camera-agnostic**: it consumes any stream that speaks **RTSP** or is
discoverable over **ONVIF**. That single decision covers nearly the whole market.

### Supported sources

| Source | How the agent connects | Notes |
|---|---|---|
| **NVR / DVR** (Dahua, Hikvision, Lorex, Amcrest, Uniview, Swann...) | ONE IP, one login, one channel per camera | **Preferred path.** 8–16 cameras from a single device. |
| **Wired IP / PoE cameras** | Direct RTSP per camera IP | Most reliable stream quality |
| **WiFi / wireless IP cameras** (Tapo, Reolink WiFi, Amcrest WiFi...) | Direct RTSP, if the model exposes it | Works, but see stability notes below |
| **Analog cameras (BNC)** | Via their DVR — DVR digitizes and serves RTSP | Old analog systems ARE supported this way |
| **Hybrid systems** | Mix of the above simultaneously | Config file can list any combination |

### NVR/DVR — the preferred integration
Pulling from the recorder is better than pulling from each camera: one credential,
one IP, no per-camera network config, and the recorder already handles the cameras.

```yaml
# Dahua/Amcrest NVR — same IP, channel per camera
- id: cam1
  rtsp_url: "rtsp://admin:PASS@192.168.1.108:554/cam/realmonitor?channel=1&subtype=1"
- id: cam2
  rtsp_url: "rtsp://admin:PASS@192.168.1.108:554/cam/realmonitor?channel=2&subtype=1"
```
```
Hikvision NVR:  rtsp://user:pass@IP:554/Streaming/Channels/{channel}02
                (channel 1 sub-stream = 102, channel 2 = 202, ...)
Dahua/Amcrest:  rtsp://user:pass@IP:554/cam/realmonitor?channel={n}&subtype=1
Uniview:        rtsp://user:pass@IP:554/unicast/c{n}/s1/live
Reolink:        rtsp://user:pass@IP:554/h264Preview_{nn}_sub
Tapo:           rtsp://user:pass@IP:554/stream2
Generic ONVIF:  discover via ONVIF, read the stream URI from the device
```

### ONVIF auto-discovery (build in Phase 2)
Rather than making customers hunt for URLs, the agent should scan the local network
via ONVIF (WS-Discovery), list every device found, and fetch each one's stream URI
automatically. The customer supplies only a username and password. **This is the
single biggest install-friction reducer in the product** — manual RTSP URLs are
where self-install fails.

Keep manual URL entry as a fallback for devices that don't advertise properly.

### NOT supported — and be honest about it up front

| Not supported | Why |
|---|---|
| **Cloud-only consumer cameras** (Ring, Nest, Arlo, Blink, most Wyze) | Deliberately expose no RTSP/ONVIF; video only reachable through the vendor's cloud/app. No local stream to read. |
| **Battery-powered wireless cameras** | They sleep and wake only on motion. There is no continuous stream to analyze, so zone/schedule detection cannot work. |

**Workaround to offer these customers:** add any cheap ONVIF-capable camera or a
small NVR alongside. Do NOT promise support you cannot deliver — it creates refunds
and bad word of mouth in a tight-knit owner community.

### Wireless stability requirements
WiFi cameras drop far more often than wired. The agent MUST:
- reconnect automatically with exponential backoff (never crash the agent)
- mark a camera `offline` in the dashboard after N failed reconnects
- alert the owner if a camera stays offline beyond a threshold (a camera that is
  "off" is also how theft gets hidden — treat downtime as a security event)
- keep all other cameras running normally while one is down

### Stream selection rule
Always prefer the **sub-stream** (subtype=1 / stream2 / lower channel) for
detection. Main streams are 4K and will destroy CPU headroom for no accuracy gain
at typical detection distances. Use the main stream only for saved alert snapshots
if higher resolution evidence is wanted.

---

## 3. Detection — What The Model Detects

One YOLOX model. It detects **objects only** — never "theft." Theft is produced by
rules layered on top (Section 6), not by the model.

### 3.1 Available from the pretrained model (COCO, zero training)

| Class | Used for |
|---|---|
| `person` | **Theft/loss detection — the core class** |
| `car`, `truck`, `bus`, `motorcycle`, `bicycle` | Drive-offs, lot/dock monitoring, vehicle counts |
| `handbag`, `backpack`, `suitcase` | Concealment context ("entered with no bag, has one now") |
| `bottle`, `cup`, `bowl` | Limited product-adjacent signals |

**Consequence: your #1 priority — theft/loss — needs NO fine-tuning.** Person and
vehicle detection work out of the box. Build Phases 1–4 on the pretrained model.

### 3.2 Requires fine-tuning (NOT in COCO)

**COCO has no `box` or `packet` class.** Shipping boxes, product packets, cartons,
and your specific SKUs are not in the pretrained model and will never be detected
without training.

To get inventory counting you must:
1. Capture ~200–300 frames of your actual boxes/packets on real shelves
2. Label them (Label Studio or CVAT, both free)
3. Fine-tune YOLOX on Google Colab's free GPU
4. Re-export to ONNX

**Sequencing verdict:** ship theft/loss on the pretrained model first. Treat
inventory counting as a second pass after Phase 4 works, because it carries a
multi-day labeling cost that theft detection does not.

### 3.3 Object tracking (required for open-hours rules)

Frame-by-frame detection cannot tell whether the person in frame 100 is the same
person from frame 40. Any rule involving **time or movement** — dwell, loitering,
exit-without-register, entered-with/left-with — needs persistent IDs.

Add **ByteTrack** (or BoT-SORT) in Phase 3. It assigns each detection a stable
`track_id` across frames. Without it, after-hours and restricted-zone rules still
work, but every open-hours behavioral rule is impossible.

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

Rules are grouped by what they need. **Tier 1 ships first — it needs no tracking and
catches a large share of real loss.** Tier 2 needs tracking (Section 3.3). Tier 3 is
deferred entirely.

### 6.1 TIER 1 — Ships in Phase 4. No tracking required.

```
should_alert(zone, detection, now):
    if detection.class == "person":
        if zone.type == "restricted": return True          # ANY time — incl. open hours
        if zone.type == "monitored":  return is_closed_hours(now)
    if detection.class in VEHICLES and zone.type == "restricted":
        return is_closed_hours(now)                         # dock/lot after hours
    return False
```

| Rule | Fires when | Catches |
|---|---|---|
| **After-hours presence** | Person in a `monitored` zone while closed | Break-ins, off-hours internal theft |
| **Restricted zone — any time** | Person in stockroom / cash office / behind counter | **Internal theft during open hours.** The strongest open-hours rule that needs no tracking. |
| **Vehicle at dock after hours** | Vehicle in a `restricted` lot/dock zone while closed | Unauthorized removal |
| **Low stock count** | `count` zone falls below `min_count` | Sweep theft, restock need |

**Cooldown/debounce (critical):** after an alert for a `(camera, zone)` pair,
suppress further alerts for that pair for `cooldown_minutes` (default 5). Events are
still logged; only the push is suppressed. One person in a zone = one alert, not
fifty.

### 6.2 TIER 2 — Open-hours behavioral rules. Requires ByteTrack. Second pass.

These make the product useful *during business hours*, when a person simply being
present is normal.

| Rule | Logic | Catches |
|---|---|---|
| **Dwell / loitering** | same `track_id` inside a zone > N minutes | Casing, cooler lingering |
| **Exit without register** | `track_id` crosses the exit line having never entered the register zone | Walk-outs — a real heuristic with no gesture AI |
| **Bag state change** | person had no `handbag`/`backpack` on entry, has one later | Concealment context |
| **Group entry** | ≥4 `track_id`s cross the entry line within N seconds | Organized retail crime (often groups) |
| **Rapid stock drop** | `count` zone falls sharply while a person is present | Grab-and-run |

**Tune conservatively.** These are heuristics, not certainties — they will produce
false positives if thresholds are aggressive. Every one of them must respect the
Gate 8 rule: under 1 false alert per site per week.

### 6.3 TIER 3 — Deferred to Phase 9. Do not attempt in v1.

**Gesture-based concealment detection** — recognizing the physical act of hiding an
item while shopping. This is a fundamentally different AI problem requiring a model
trained on years of real theft footage. It is the incumbent's moat (Veesion has built
it since 2018). Attempting it in v1 will consume months and produce nothing shippable.

**The honest framing:** for after-hours loss and internal theft — which is where much
of a small store's shrink actually comes from — Tiers 1 and 2 catch more than gesture
detection would.

---

## 7. License, Verification & Limits System

### 7.1 License key model

Every site gets a **license key** bound to one installed agent.

```
license_key:  STOREV-XXXX-XXXX-XXXX-XXXX   (generated on subscription)
bound to:     site_id + device_fingerprint (hashed hostname+MAC+OS)
```

**Device binding / verification:** on first activation the agent sends its
fingerprint. The server stores it. If the SAME key later activates from a
DIFFERENT fingerprint, reject it (prevents one key running on many machines).
Provide a "deactivate device" action in the dashboard so a customer can legitimately
move to a new PC.

### 7.2 License states

| State | Meaning | Agent behavior |
|---|---|---|
| `active` | Subscription paid, valid | Full operation |
| `grace` | Expired < 3 days ago | **Still runs**, but shows a warning + daily push alert |
| `suspended` | Expired ≥ 3 days | **ALL cameras stop.** Detection halts. |
| `revoked` | Manually disabled | All cameras stop immediately, no grace |

### 7.3 The 3-day grace + auto-shutoff (core requirement)

```
# agent checks in daily (and on every start)
check_license():
    try:
        resp = POST /license/validate {license_key, device_fingerprint}
        cache_token(resp.token, resp.expires_at, resp.state)
    except no_internet:
        resp = read_cached_token()          # offline-tolerant

    now = utc_now()

    if resp.state == "active" and now < resp.expires_at:
        enable_all_cameras()
        return RUNNING

    days_past = (now - resp.expires_at).days

    if days_past < 3:
        enable_all_cameras()                 # GRACE — keeps working
        show_warning(f"License expired. Cameras stop in {3 - days_past} day(s).")
        send_push_alert("Renew to avoid shutdown")
        return GRACE

    # >= 3 days past expiry
    stop_all_cameras()                       # close every RTSP stream
    halt_detection()
    show_blocking_message("License expired — renew to resume monitoring")
    return SUSPENDED
```

**Critical detail — the offline loophole.** The cached token carries its own
`expires_at`. An agent that never reaches the server simply runs down its cached
token and then enters grace → suspended on schedule. **Unplugging the internet does
NOT grant unlimited free use.** This is what makes offline-first and subscription
enforcement coexist.

**While suspended, the agent keeps doing exactly one thing:** retrying
`/license/validate` every 30 minutes. Nothing else runs.

### 7.4 Auto-resume on renewal

```
# Stripe webhook -> Supabase Edge Function
on invoice.payment_succeeded:
    set license.state   = "active"
    set license.expires_at = now + billing_period
on invoice.payment_failed / subscription.deleted:
    set license.state = "expired" (expires_at unchanged -> grace clock starts)
```

The suspended agent's next 30-minute poll returns `active`, it caches the new
token, **reopens all camera streams and resumes detection automatically.** No
reinstall, no manual step, no support call. This is a hard requirement.

### 7.5 Verification system

| Verification | When | Why |
|---|---|---|
| **Email verification** | Signup (handled by Clerk) | No fake accounts |
| **Device fingerprint** | Agent activation | One key = one machine |
| **Agent key auth** | Every API call from agent | Only real agents write data |
| **Payment verification** | Stripe webhook | License state follows payment truth |
| **Site ownership** | Adding a site | Site count must fit the tier |

### 7.6 Tier limits (enforced in BOTH places)

Limits must be enforced **server-side** (API rejects over-limit writes) AND
**agent-side** (agent refuses to open more cameras than allowed). Server-side alone
can be bypassed; agent-side alone can be patched.

| Tier | Locations | Cameras/site | Users | History |
|---|---|---|---|---|
| Free | 1 | 2 | 1 | 7 days |
| Single | 1 | 8 | 2 | 30 days |
| Double | 2 | 8 | unlimited | 90 days |
| Many | unlimited | 12 | unlimited | 365 days |

```
enforce_limits(site):
    tier = get_tier(site.customer_id)
    if count_sites(customer) > tier.max_locations:  block new site
    enabled = camera list from config
    if len(enabled) > tier.max_cameras:
        enable only the first tier.max_cameras, log + warn in dashboard
```

**History retention:** a scheduled job deletes events/snapshots older than the
tier's window. This is also what keeps your Supabase storage costs near zero.

**Never gate detection accuracy by tier.** Gate locations, cameras, users, history,
and analytics depth only.

---

## 7b. Trial → Purchase → Activation → Renewal (customer lifecycle)

The complete flow from download to paid, and what happens when it lapses.

```
DOWNLOAD → INSTALL → 7-DAY TRIAL → EXPIRY PROMPT → BUY ON WEBSITE
    → RECEIVE KEY → PASTE IN APP → ACTIVE → EXPIRY WARNING
    → RENEW (key extends) → ACTIVE ...   or   → NO RENEWAL → STOPPED
```

### 7b.1 Trial (7 days, no key, no payment)

On first launch the agent registers itself and receives a 7-day trial token.

```
first_launch():
    fp = device_fingerprint()
    resp = POST /trial/start {fingerprint: fp, machine_info}
    if resp.status == "granted":
        cache_token(state="trial", expires_at=now+7d)
    if resp.status == "already_used":
        show("Trial already used on this device — enter a license key")
        require_license_key()
```

**Anti-abuse (this is the part that matters).** The server permanently records the
fingerprint. Uninstall + reinstall on the same machine does **NOT** grant a new
trial. Also rate-limit trials per IP and per email to blunt fingerprint spoofing.

**Trial requires one-time internet access to activate.** A fully offline install
cannot start a trial — otherwise the trial is trivially farmed. After activation
the trial runs offline normally for its 7 days.

**Trial is full-featured but capped:** all detection features, limited to **1 site,
2 cameras** (matches the Free tier). Never cripple accuracy — an owner must see the
product at its real quality or the trial proves nothing.

**Day 5 and day 6:** in-app banner + push: "Trial ends in N days."

### 7b.2 Trial expiry → purchase

At day 7 the agent **stops detection immediately — no grace for trials** (grace is
a courtesy for paying customers, not free users) and shows a blocking screen:

```
  Your 7-day trial has ended.
  [ Buy a license ]   [ I already have a key ]
```

**"Buy a license"** opens the browser to `https://[yourdomain]/buy?fp=<fingerprint>`
— carrying the fingerprint so the purchased key can be pre-bound and the customer
never has to copy it manually if they buy on the same machine.

### 7b.3 Purchase page (on your website)

Customer picks a plan and duration; Stripe Checkout handles payment.

| Duration | Billing | Notes |
|---|---|---|
| Monthly | Stripe subscription (auto-renew) | Default — best for you (no churn at each expiry) |
| Yearly | Stripe subscription (auto-renew), ~2 months free | Best cash flow; push this |
| Custom (3/6 mo) | One-time payment | For customers who refuse auto-renew |

On `checkout.session.completed`, a Supabase Edge Function:
1. generates `license_key` = `STOREV-XXXX-XXXX-XXXX-XXXX`
2. inserts a `licenses` row: `state=active`, `expires_at = now + duration`, tier
3. emails the key **and** shows it on a success page and in the customer dashboard

### 7b.4 Activation in the app

```
activate(key):
    resp = POST /license/activate {license_key: key, fingerprint: fp}
    -> "activated": bind fp to key, cache signed token, START DETECTION
    -> "already_bound_other_device": show "This key is in use on another
       computer. Deactivate it in your dashboard first."
    -> "invalid" / "expired": show reason
```

Activation requires internet **once**. After that the agent runs offline on the
cached signed token until it needs to re-verify.

### 7b.5 Renewal — extend the SAME key

**Verdict: never issue a new key on renewal.** Extend `expires_at` on the existing
key. A customer who never has to re-enter anything never files a support ticket.

- **Auto-renew (subscription):** Stripe `invoice.payment_succeeded` → Edge Function
  extends `expires_at`. The agent's next check-in gets the new token. **The customer
  does nothing and notices nothing.** This is why you push monthly/yearly
  subscriptions over one-time purchases.
- **One-time purchase:** at expiry the app shows `[ Renew ]` → browser →
  `/renew?key=<key>` → payment → same key extended → next poll picks it up.

### 7b.6 Expiry warnings and shutdown

| When | Behavior |
|---|---|
| 7 days before expiry | In-app banner + email |
| 3 days / 1 day before | Push alert + email |
| Expiry day (`grace` begins) | Detection **continues**; daily warning: "Cameras stop in N days" |
| 3 days past expiry (`suspended`) | **ALL cameras close. Detection halts.** Blocking renew screen. |

**Paid customers get the 3-day grace; trials get none.** The grace exists to absorb
an expired card or a failed payment retry — it protects a paying customer from
losing security coverage over a billing hiccup. Stripe retries failed payments
inside that same window.

**While suspended:** the agent polls `/license/validate` every 30 minutes and does
nothing else. On a successful renewal it re-derives the model key, reopens every
camera, and resumes automatically — no reinstall, no support call.

### 7b.7 Endpoints this flow needs

```
POST /trial/start        {fingerprint, machine_info} -> {status, token, expires_at}
POST /license/activate   {license_key, fingerprint}  -> {status, token, expires_at}
POST /license/validate   {license_key, fingerprint}  -> {state, token, expires_at}
POST /license/deactivate {license_key}               -> frees device binding
POST /webhooks/stripe    (checkout.session.completed, invoice.payment_succeeded,
                          invoice.payment_failed, customer.subscription.deleted)
GET  /buy?fp=            purchase page
GET  /renew?key=         renewal page
```

### 7b.8 Website pages required

`/` landing · `/pricing` · `/download` · `/buy` · `/renew` · `/dashboard` (sites,
license status, device deactivation, billing portal) · `/docs` install guide ·
`/support`

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

### Cloud (Supabase / PostgreSQL) — enable Row Level Security on every table
```
customers(id, clerk_org_id, name, tier, stripe_customer_id, stripe_subscription_id)
sites(id, customer_id, name, agent_key, location, last_seen)
cameras(id, site_id, name)
zones(id, camera_id, name, type, polygon)
lines(id, camera_id, name, points, direction)
events(id, site_id, camera_id, zone_id, ts, object_class, confidence, snapshot_url)
counts(id, site_id, camera_id, zone_or_line_id, ts, object_class, count)
announcements(id, customer_id, site_id_or_null, author, text, ts)
licenses(site_id, license_key, state, expires_at, device_fingerprint, activated_at)
   -- state: active | grace | suspended | revoked
license_events(id, site_id, ts, old_state, new_state, reason)   -- audit trail
users -- owned by Clerk; store only clerk_user_id references
```

**RLS rule:** every query is scoped by `customer_id` derived from the Clerk
session. A customer must never be able to read another customer's rows.

---

## 11. Cloud API — Endpoints

- `POST /events` — batch of events from an agent (auth: agent_key).
- `POST /counts` — batch of counts from an agent.
- `POST /license/validate` — body `{license_key, device_fingerprint}` ->
  `{token, state, expires_at}`. Runs as a Supabase Edge Function. Also performs
  device binding on first activation.
- `POST /webhooks/stripe` — Stripe events; flips license state on payment
  success/failure. Must verify the Stripe signature.
- `GET /limits` — current tier limits for the customer (agent + dashboard read this).
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
7. **Billing** — current tier, usage vs limits, Stripe billing portal link.
8. **License status** — per site: state badge (active/grace/suspended), expiry
   date, days remaining, device bound, "deactivate device" action.

Tables and thumbnails first; charts on the reports screen once data flows.

---

## 13. Build Order — 8 Phases (build and TEST each before the next)

Do everything up to Phase 8 on your OWN home camera. It is free and instant.

1. **Multi-object detection core** — YOLOX (ONNX) detecting person, vehicle, and
   box/packet on a video clip. Prove on real footage. Fine-tune only if it misses.
2. **Live camera ingestion** — read 5-6 RTSP streams, round-robin sampling.
3. **Zones + lines + counting + TRACKING** — point-in-polygon zones, counting lines,
   count logic, and **ByteTrack for persistent track_ids** (Section 3.3). Tracking is
   required for all Tier 2 open-hours rules and for accurate counting (without it you
   double-count the same person every frame).
4. **Theft/loss rules + logging** — schedule, **Tier 1 alert rules (Section 6.1)**,
   cooldown, SQLite. THEFT ALERTS GO LIVE HERE (your first priority, working).
   Tier 2 open-hours rules come as a second pass after Tier 1 is trustworthy.
5. **Announcements** — automatic push alerts (FCM) + staff message board.
6. **Cloud spine** — Supabase schema + RLS, Vercel API routes for /events and
   /counts, agent sync with offline buffering. No billing yet.
7. **Auth + dashboard + reports** — Clerk auth and organizations, Next.js dashboard
   on Vercel (sites, feed, reports, announcements, search), reports from logged data.
7b. **License + limits + billing** — license keys, device binding, 3-day grace and
   auto-shutoff, auto-resume on renewal, tier limit enforcement (server AND agent),
   Stripe subscriptions + webhooks + billing portal.
8. **Real deployment + tuning** — remote-install agent on ONE USA site, connect
   its cameras, set zones/hours, run several days, KILL FALSE POSITIVES.

After Phase 8: roll to 4-5 more of the 17 sites, log dollars saved, then raise.

---

## 14. Deferred to phases 9-10 (do NOT attempt in the 8 phases)

- **Phase 9 — Gesture-based shoplifting detection** (spotting item concealment).
  A different, hard AI problem needing a custom-trained model. Veesion's moat.
  Build only after the core platform is proven and earning. See Section 6.3.
- **Phase 10 — SKU / product-level recognition** (identifying WHICH product, not
  just "a box"). Needs custom training per product.
  NOTE: even generic box/packet detection needs fine-tuning (Section 3.2) — COCO has
  no box class. Theft/loss works pretrained; inventory does not.

Also later: Stripe billing + subscription tiers, self-serve installer, SMS/voice
alerts, multi-tenant onboarding polish, exotic NPU chip support.

Keep the 8 phases focused. Cramming phases 9-10 into them is what breaks timelines.
