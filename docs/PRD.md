# Product Requirements Document — [PRODUCT NAME TBD]

**Version:** 1.0
**Date:** July 2026
**Owner:** Founder / AI Developer
**Status:** Pre-build. Day 1.

---

## 1. One-Line Summary

AI software that turns the cameras a store already owns into a system that alerts
the owner the moment theft happens — plus counts inventory, tracks traffic, and
delivers a daily report. Affordable, works with any camera, keeps running offline.

---

## 2. The Problem

**Core problem statement:**
> Store cameras RECORD theft but do not STOP it. Owners find out the next morning —
> after the loss, too late to act, facing hours of footage to scrub.

The gap is between **recording** and **knowing in time**.

**Who feels it:** US gas station and local shop owners with 2–10 locations. They
have cameras. They have no one watching the feeds. They cannot afford enterprise
security software or a guard.

**Specific pains, ranked by how much they hurt:**
1. Fuel drive-offs — pure cash loss, discovered after the car is gone
2. Employee/internal theft — suspected, never proven
3. Grab-and-run — cooler to door in seconds; recording is worthless
4. After-hours break-ins — learned about at 7am
5. Lone night-shift clerk safety — nobody watching in real time

**Market context:** US retailers lose ~$47B/year to shrink (~2% of revenue). The
AI retail theft deterrence market is ~$3.12B in 2026, growing ~19% CAGR to ~$6.26B
by 2030.

---

## 3. Why Now / Why Us

- Industry spend is shifting from hardware to **software intelligence**.
- **Edge processing** (running AI at the store, not the cloud) is where the market
  is heading — matches our architecture exactly.
- Privacy regulation is tightening; **no-facial-recognition, on-device** design is
  becoming a compliance advantage, not just a preference.
- Enterprise vendors (Spot AI, Veesion, Lumana, Solink) chase mid/large chains with
  "contact sales" pricing. **Small operators are abandoned.** That's the gap.

**Our unfair advantages:**
1. Founder operates 17 locations — we ARE the customer, and we get free real-world
   deployment sites and training data.
2. Existing distribution/connections into US gas stations and local shops.
3. Near-zero build cost (open-source stack, customer-owned hardware).

---

## 4. Target User

**Primary persona — "The multi-site owner"**
- Owns 2–10 gas stations or convenience/local shops in the US
- Runs them himself; no corporate security team; decides purchases alone
- Open late or 24h; already has DVR/NVR cameras (often Dahua/Hikvision)
- Hands-on, knows his numbers, price-sensitive but pays for what stops bleeding
- **Highest-intent trigger: had a theft incident recently**

**Explicitly NOT targeting in v1:** single-store owners (too price-sensitive),
national chains (enterprise procurement), non-US markets.

---

## 5. Product Vision

Three-year vision: the default "store intelligence" layer for independent US gas
stations and small shops — security, inventory, and operations from cameras they
already own, at a price any small operator can afford.

**Positioning:** "Your phone buzzes the moment it happens — not the next morning.
Using the cameras you already have."

**Non-negotiable principles:**
- Works with EXISTING cameras (ONVIF/RTSP). Never require new hardware.
- Detects ACTIONS, not identities. **No facial recognition, ever.**
- Keeps working with no internet.
- Transparent, self-serve pricing. No "contact sales."
- An alert must mean something. Trust > feature count.

---

## 6. v1 Scope (SHIPPING)

v1 includes the full platform. **Internal build order still ships theft first** —
see Section 10 — but v1 is not "done" until all four capability areas work.

### 6.1 Theft & Loss Detection (PRIMARY)
- Detect people and vehicles on live camera feeds — **works on the pretrained model,
  no training required**
- **Object tracking (ByteTrack)** for persistent IDs — required for open-hours
  behavioral rules and accurate counting
- **Zones**: user-drawn regions per camera, typed `restricted` / `monitored` / `count`
- **Schedule**: per-site open/closed hours
- **Rules**: restricted zone = alert any time; monitored zone = alert when closed;
  vehicle in restricted dock/lot zone = alert when closed
- **Push alert** to phone with snapshot, within seconds
- **Cooldown/debounce** so one event = one alert, not fifty

### 6.2 Counting & Inventory
- **Zone counts**: how many boxes/items visible in a defined zone
- **Line counts**: items or people crossing a defined line (receiving door, entrance)
- Counts logged over time; optional **low-count alert** below a threshold

### 6.3 Daily Reports
- Auto-generated per site and across all sites
- Contents: alerts raised, incidents by type, items received, peak traffic hours,
  vehicle counts
- Viewable in dashboard; delivered each morning

### 6.4 Announcements
- **Automatic**: rule-triggered alerts (theft, after-hours, low stock)
- **Staff board**: staff post text messages, visible per-site or all-sites

### 6.5 Camera Compatibility
Works with **every camera category** via ONVIF/RTSP:
- **NVR/DVR** (Dahua, Hikvision, Lorex, Amcrest, Uniview, Swann) — preferred path:
  one IP, one login, a channel per camera
- **Wired PoE IP cameras** — direct RTSP
- **WiFi/wireless IP cameras** — direct RTSP where the model exposes it
- **Analog BNC cameras** — supported through their DVR
- **ONVIF auto-discovery** — agent scans the network and finds cameras itself;
  customer supplies only username + password. Biggest install-friction reducer.

**Not supported (state up front):** cloud-only consumer cameras (Ring, Nest, Arlo,
Blink, most Wyze) expose no local stream; battery cameras sleep and have no
continuous stream to analyze. Offer these customers a cheap ONVIF camera or NVR.

**Camera downtime = security event.** A camera going offline is how theft gets
hidden. Alert the owner if one stays down past a threshold.

### 6.6 Platform
- Agent installs on a PC at each site; connects 5–6 cameras (sub-stream)
- Local SQLite buffer; syncs to cloud when online; **never blocks on sync**
- Web dashboard: all sites, event feed, reports, announcements, search, billing
- Multi-tenant accounts (Clerk organizations)

### 6.7 License, Verification & Limits
- **License key per site**, bound to one device fingerprint (one key = one machine,
  with a "deactivate device" action for legitimate PC changes)
- **States:** `active` → `grace` (< 3 days past expiry: still runs, warns daily) →
  `suspended` (≥ 3 days: **ALL cameras stop, detection halts**) → `revoked`
- **Auto-resume:** Stripe webhook flips state on payment; the suspended agent's next
  30-minute poll reopens every camera automatically. No reinstall, no support call.
- **Offline loophole closed:** the cached token carries its own expiry, so an agent
  that never phones home runs down its clock and suspends on schedule. Unplugging
  the internet does not grant free use.
- **Verification:** email (Clerk), device fingerprint, agent key on every API call,
  Stripe payment truth, site-count check
- **Tier limits enforced BOTH server-side and agent-side** (server alone gets
  bypassed; agent alone gets patched)

---

## 7. Explicitly OUT of v1

| Deferred | Why |
|---|---|
| Gesture-based shoplifting detection (concealment) | Different, hard AI problem; needs custom-trained model. Competitor moat. Phase 9. Tier 1+2 rules (SPEC §6) catch more of a small store's actual shrink anyway. |
| SKU/product-level recognition | Needs per-product training. "Count objects" ships; "identify products" waits. Phase 10. |
| SMS/voice alerts | Push (FCM) is free and sufficient for v1. Twilio costs money per message. |
| Facial recognition | Deliberate permanent exclusion. Privacy/legal risk, unnecessary. |
| Self-serve installer + onboarding polish | v1 uses assisted/remote install. |
| Exotic NPU chip support | ONNX covers mainstream hardware. Add per-chip on demand. |

---

## 8. Success Metrics

**v1 (own 17 sites) — must hit before selling externally:**
- Deployed and running on 5+ own sites
- **False positives < 1 per site per week** (HARD GATE — do not sell until met)
- Agent uptime > 95%; survives camera drop + internet drop without crashing
- Alert latency < 10 seconds from event to phone
- **A hard ROI number**: incidents caught / shrink reduction over 90 days

**Post-v1 (commercial):**
- 5–10 paying external customers from network
- 3-month retention > 80%
- Customer-reported "alerts I trust" > "alerts I ignore"

---

## 9. Technical Architecture (summary)

Full technical spec lives in `SPEC.md`. Summary:

- **Edge Agent** (Python 3.12): OpenCV reads RTSP/ONVIF → **YOLOX** model exported
  to **ONNX**, run via **ONNX Runtime** (GPU if present, CPU fallback) → zone/rule
  logic → FCM push → SQLite → sync
- **Cloud**: **Supabase** (PostgreSQL + storage + RLS) and **Vercel** (dashboard +
  API routes). **Supabase Edge Functions** for license validation and Stripe
  webhooks. No VM to maintain; free tiers cover the first 17 sites.
- **Auth**: **Clerk** (identity + organizations). Rule: **Clerk owns identity,
  Supabase owns data.** Never build a second login path.
- **Dashboard**: **Next.js** on Vercel
- **Billing**: **Stripe** subscriptions + webhooks + billing portal
- **MCP servers for Claude Code**: Supabase, Vercel, Stripe, Clerk — so Claude Code
  reads the real schema and deploys directly instead of guessing. Never commit
  service-role or live secret keys.

**Licensing constraint:** YOLOX (Apache-2.0) — NOT Ultralytics YOLO (AGPL would
force open-sourcing the product).

**Performance:** round-robin frame sampling (default one frame per camera every
2s). Use camera SUB-STREAM, not main stream. This is what makes 5–6 cameras viable
on a normal PC.

---

## 10. Build Phases

Build and TEST each before starting the next. Everything through Phase 7 is
developed on the founder's own home camera.

| Phase | Deliverable | Done when |
|---|---|---|
| 1 | Multi-object detection (person, vehicle, box) on video clips | Correct boxes on real footage |
| 2 | Live RTSP ingestion, 5–6 cams, round-robin sampling | Survives camera unplug; benchmark passes |
| 3 | Zones, lines, counting logic | Counts people/boxes/cars correctly in zones |
| 4 | **Theft/loss rules + alerts + SQLite** | **Phone buzzes on a real zone/after-hours event** |
| 5 | Announcements (auto + staff board) | Both alert types working |
| 6 | Cloud spine: Supabase schema + RLS, Vercel API routes, agent sync | Events reach cloud; works offline and catches up |
| 7 | Clerk auth + Next.js dashboard + reports | All sites visible in one place with reports |
| 7b | License keys, 3-day grace + auto-shutoff, auto-resume, tier limits, Stripe | Expiry stops cameras; renewal resumes them automatically |
| 8 | Real deployment + false-positive tuning | 1 US site live, alerts trustworthy |

**After Phase 8:** roll to 4–5 more own sites, run 90 days, produce the ROI number.

---

## 11. Pricing (locked)

Tiered by location count. Gate **locations, cameras, history, and analytics depth**
— NEVER gate detection accuracy.

| Tier | Price | Locations | Includes |
|---|---|---|---|
| **Free (Starter)** | $0 | 1 | 2 cameras, theft alerts + people counting, 7-day history |
| **Single** | $39/mo | 1 | 8 cameras, all features, 30-day history, 2 users |
| **Double** | $69/mo | 2 | All features, 90-day history, unlimited users |
| **Many** | $29/location/mo | 3+ | Multi-site analytics, 1-year history, API, priority support |

**Enforced limits per tier:**

| Tier | Locations | Cameras/site | Users | History |
|---|---|---|---|---|
| Free | 1 | 2 | 1 | 7 days |
| Single | 1 | 8 | 2 | 30 days |
| Double | 2 | 8 | unlimited | 90 days |
| Many | unlimited | 12 | unlimited | 365 days |

History retention is also cost control — a scheduled job deletes events and
snapshots past the tier window, keeping Supabase storage near zero.

Rationale: incumbents charge $200–500/mo for theft ALONE with "contact sales"
pricing. We publish a price, undercut heavily, and deliver more.

---

## 12. Go-To-Market (post-v1)

**Sequence:** own 17 sites → ROI number → network pilots → paid customers.

- **Channel 1 (primary): direct outreach via founder's connections.** Warm intros
  close B2B. Prioritize owners with MULTIPLE locations and recent theft incidents.
- **Channel 2: LinkedIn authority.** Positioned as the AI developer building
  affordable theft detection for gas stations. Credibility layer, not sales channel.
- **Channel 3: referrals.** Word-of-mouth store-to-store; build referral reward in
  from day one.
- **Onboarding:** assisted/remote install in v1. Every early customer must succeed.

**Not doing:** paid ads, TikTok/Instagram, cold enterprise sales.

---

## 13. Risks & Mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| **Never ships** (biggest risk) | Critical | Phase gates; ship Phase 1 in week 1; no new features until phase done |
| **False positives destroy trust** | Critical | Hard gate: <1/site/week before any external sale. Cooldown logic. Tune on real footage. |
| **No moat / copyable** | High | Build proprietary training data from own 17 sites; niche-dominate gas stations |
| Scope creep (v1 is broad) | High | Section 7 is binding. Theft ships first (Phase 4) even within v1. |
| Solo + remote execution | High | Hire one strong engineer AFTER ROI proof, not before |
| Weak PC can't handle 6 cams | Medium | Sub-stream + sampling; benchmark mode; add used GPU (~$150–250) only where needed |
| Privacy/legal exposure | Medium | No facial recognition. On-device processing. Proper privacy policy + terms before selling. |
| Unsupported camera promises | Medium | State cloud-only/battery limits up front; offer ONVIF camera or NVR instead. Refunds and bad word-of-mouth spread fast in this community. |
| Billing built too early | Medium | Licensing/Stripe is Phase 7b — after detection is trustworthy. Own 17 sites need no enforcement. |
| Funded competitor enters segment | Medium | Move fast; own the niche; data advantage compounds |

---

## 14. Immediate Next Actions (Day 1)

1. **Regain access to test camera** (Dahua H5A @ 192.168.100.134) — DMSS "Forgot
   Password" or physical factory reset. **This is the current blocker.**
2. Set new device password: **letters and numbers only** (special chars break RTSP)
3. Verify RTSP URL in VLC:
   `rtsp://admin:PASSWORD@192.168.100.134:554/cam/realmonitor?channel=1&subtype=1`
4. Install Python 3.12, Git, Node.js, VS Code, Claude Code
5. Create project folder with `PRD.md` + `SPEC.md`; start Claude Code there
6. Run Phase 1 prompts → detection working on own footage

**The rule for the next 60 days:** no fundraising, no selling, no new features.
Ship phases 1–8, deploy to own sites, produce the ROI number. Everything else waits.
