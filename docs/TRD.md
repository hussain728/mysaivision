# Technical Requirements Document — [PRODUCT NAME TBD]

**Version:** 1.0 | **Date:** July 2026 | **Status:** Pre-build

Companion documents: `PRD.md` (business/product) and `SPEC.md` (feature spec and
build order). This TRD defines the **engineering contract**: performance targets,
security, media handling, licensing enforcement, failure behavior, and acceptance
criteria. Where this document and SPEC.md disagree, **this document wins.**

---

## 1. System Overview

Three deployable units:

| Unit | Tech | Runs on |
|---|---|---|
| **Edge Agent** | Python 3.12, ONNX Runtime, OpenCV, SQLite | Customer PC at each site |
| **Cloud** | Supabase (Postgres/Storage/Edge Functions) + Vercel (Next.js API) | Managed |
| **Client** | Next.js PWA (mobile app later) | Browser / phone |

Trust boundary: **the agent runs on hardware we do not control.** Every rule in
Section 6 follows from that fact.

---

## 2. Performance Requirements

| Requirement | Target | Hard limit |
|---|---|---|
| Cameras per agent | 6 | 12 |
| Detection latency (frame → decision) | < 500 ms | < 1500 ms |
| Alert latency (event → phone) | < 5 s | < 10 s |
| Sampling interval per camera | 2 s | configurable 1–10 s |
| Agent RAM | < 2 GB | < 4 GB |
| Agent CPU (6 cams, CPU-only) | < 70% sustained | < 85% |
| Cloud API p95 response | < 300 ms | < 1 s |
| Dashboard first paint | < 2 s | < 4 s |

**Mandatory implementation rules:**
- **Sub-stream only** for detection (`subtype=1` / `stream2`). Main stream is used
  only for on-demand clip retrieval.
- **Round-robin sampling** — never process every frame of every camera.
- **One reader thread per camera** holding only the newest frame; the loop reads
  that. Sequential reads fall behind and analyze stale footage.
- ONNX Runtime selects `CUDAExecutionProvider` if available, else CPU. Log which
  at startup.
- Agent ships a **benchmark mode** that measures the host and reports whether it
  can sustain the configured camera count; installer refuses/warns below minimum.

**Minimum host spec:** 4-core x86-64 CPU, 8 GB RAM, 50 GB free disk, wired network.
Recommended for 6+ cameras: any NVIDIA GPU with 4 GB+ VRAM.

---

## 3. Media & Evidence Handling

**Decision: snapshot pushed with the alert; full clip retrieved on demand.**
This keeps bandwidth and storage near zero while preserving evidence quality.

### 3.1 Snapshot (immediate)
- Captured at alert time, annotated with the detection box
- JPEG, longest edge ≤ 1280 px, quality 80, target < 200 KB
- Uploaded to Supabase Storage with the event; shown in push + dashboard

### 3.2 Clip (on demand)
- Agent maintains a **rolling local buffer** per camera: last 120 seconds,
  sub-stream, written to disk in rotating segments
- On alert, the agent records the buffer window `[-15s, +15s]` around the event to
  a local clip file and stores its path on the event row. **It does not upload.**
- Dashboard "Get clip" → cloud sends a fetch command → agent uploads that clip →
  cloud returns a signed URL. Typical availability: < 60 s if the agent is online.
- If higher quality is requested and the recorder supports it, pull the same time
  window from the **main stream** instead.

### 3.3 Retention
- Local clips: rolling, capped at a configurable disk budget (default 20 GB),
  oldest deleted first. Local clips expire after 30 days regardless.
- Cloud snapshots and uploaded clips: deleted per the customer's tier history
  window (7 / 30 / 90 / 365 days) by a scheduled job.
- Disk-full is a **non-fatal** condition: stop writing clips, keep detecting, raise
  a dashboard warning.

---

## 4. Alert Delivery

**Phase 1: web push (PWA). Native apps later.** Same backend serves both.

- **Firebase Cloud Messaging** for Web Push now; the same FCM tokens work for
  iOS/Android apps later — no re-architecture needed.
- PWA must be installable (manifest + service worker) so owners get a home-screen
  icon and background notifications.
- **Email fallback is required**, not optional: if no push token is registered or
  push delivery fails, send email. An undelivered theft alert is a product failure.
- Payload: site, camera, zone, event type, timestamp, snapshot URL, deep link.
- Per-user, per-site notification preferences (which zones, which hours).
- **Delivery must never block detection.** Queue and retry with backoff.

---

## 5. Reliability & Failure Behavior

The agent runs unattended in a shop. It must never require someone on site.

| Failure | Required behavior |
|---|---|
| One camera drops | Reconnect with exponential backoff (1s→60s cap), forever. Other cameras unaffected. |
| Camera offline > 15 min | Mark offline in dashboard **and alert the owner — a disabled camera is a security event** |
| Internet drops | Detection and alerts-to-local continue. Events queue in SQLite. Sync resumes and backfills automatically. |
| Cloud unreachable | Never blocks detection. Never crashes. |
| Model fails to load | Fatal, but retry 3× then exit with a clear logged reason and non-zero code so the service manager restarts it |
| Disk full | Stop writing clips, keep detecting, warn |
| Agent crash | Runs as a **service** (Windows Service / systemd) with auto-restart on failure and start-on-boot |
| Power loss | Auto-start on boot; SQLite in WAL mode so no data loss |

**Targets:** agent uptime ≥ 99% monthly; zero data loss for events already written
to SQLite; recovery from any transient failure without human intervention.

---

## 6. Licensing, Anti-Piracy & Enforcement

### 6.1 The honest constraint — read this first

Software that runs offline on hardware you do not control **cannot be made
uncrackable.** Python is especially easy to reverse-engineer. Anyone who tells you
otherwise is selling something.

**So the goal is not "impossible to crack." The goal is: make cracking cost more
effort than the $39/month subscription is worth.** That defeats ~95%+ of real risk,
which is casual non-payment, not determined attackers. Do not spend engineering
months chasing the last 5% — spend it on detection reliability instead.

### 6.2 Enforcement layers (implement all five)

**Layer 1 — Encrypted model (strongest lever).**
The ONNX model is the product's value. Ship it **AES-encrypted**. The decryption key
is derived from the signed license token and the device fingerprint, and the model
is decrypted **into memory only** — never written to disk in plaintext.
**No valid license → no usable model → no detection.** This makes a cracked binary
useless rather than merely unlocked.

**Layer 2 — Signed license tokens.**
Server signs tokens with a private key (Ed25519/RS256). The agent verifies with an
embedded public key. Tokens carry `site_id`, `device_fingerprint`, `state`,
`expires_at`, `tier_limits`. Tokens are unforgeable without the private key, which
never leaves the server.

**Layer 3 — Device binding.**
Fingerprint = hash(machine GUID + primary MAC + OS install ID). Bound at first
activation. A different fingerprint with the same key is rejected. Dashboard offers
a **"deactivate device"** action for legitimate hardware changes (limit ~3
reactivations per 90 days, then support).

**Layer 4 — Compiled, obfuscated binary.**
Package with **PyInstaller** (one-file) plus bytecode obfuscation. Strip symbols.
**Code-sign** the Windows executable — this also prevents SmartScreen warnings that
would otherwise wreck self-install conversion. Raises effort; not a wall on its own.

**Layer 5 — Server-side truth.**
License state lives in Supabase, driven by Stripe webhooks. The agent is never the
authority on whether a subscription is paid.

### 6.3 State machine and the 3-day rule

```
active    → subscription valid                  → all cameras run
grace     → < 3 days past expiry                → cameras run + daily warning push
suspended → ≥ 3 days past expiry                → ALL cameras closed, detection halts
revoked   → manually disabled                   → immediate stop, no grace
```

**Closing the offline loophole (critical).** The cached token carries its own
`expires_at`. An agent that never reaches the server simply runs the cached token
down, enters `grace`, then `suspended`, on schedule. **Disconnecting the network
does not grant free use.** Anti-rollback: persist the highest-seen UTC timestamp;
if system time moves backwards significantly, treat it as tampering and suspend.

**While suspended:** the agent does exactly one thing — poll `/license/validate`
every 30 minutes. No streams open, no detection, no writes.

**Auto-resume (hard requirement):** Stripe `invoice.payment_succeeded` → Edge
Function sets `state=active`, extends `expires_at` → the suspended agent's next
poll receives it, re-derives the model key, **reopens all cameras and resumes
automatically.** No reinstall, no manual step, no support ticket.

### 6.4 Tier limits — enforced in BOTH places
Server rejects over-limit writes (sites, cameras, users). Agent refuses to open
more than `tier_limits.max_cameras` streams. Server-only can be bypassed by a
patched agent; agent-only can be patched. Both is the requirement.

---

## 7. Security Requirements

- **No facial recognition. Ever.** Detect actions, not identities. Product,
  privacy, and legal decision — not a toggle.
- Video is processed **locally**. Raw video never leaves the site except an
  explicitly requested clip.
- TLS 1.2+ for all transport. Agent pins the API certificate.
- **Camera credentials encrypted at rest** on the agent (OS keystore: DPAPI on
  Windows, libsecret/keyring on Linux). Never plaintext in `config.yaml`.
- Agent authenticates every API call with a per-site key; keys are rotatable and
  revocable from the dashboard.
- **Supabase Row Level Security on every table**, scoped by `customer_id` derived
  from the Clerk session. A customer must never read another customer's rows.
- Snapshots/clips served only via short-lived signed URLs (≤ 15 min).
- Stripe webhook signature verification is mandatory.
- Secrets in `.env.local`, never committed. Service-role and Stripe secret keys
  never reach the client bundle or an MCP config that gets committed.
- Audit log for security-relevant actions: license state changes, device
  deactivation, key rotation, user invites.

---

## 8. Packaging & Deployment

**Verdict: native installer, not Docker.** Your buyers are shop owners, not
engineers. Docker would generate support calls that cost more than the subscription.

- **Windows:** signed `.exe` installer (Inno Setup or MSI). Installs as a Windows
  Service, auto-start on boot, auto-restart on failure.
- **Linux:** `.deb` + systemd unit (for the technical minority).
- Installer flow: license key → **ONVIF network scan** → camera credentials →
  benchmark host → warn if under-spec → activate → start service.
- **ONVIF auto-discovery is required, not optional.** Manual RTSP URL entry is the
  single biggest self-install failure point; keep it only as fallback.
- **Auto-update:** agent checks for updates daily, downloads signed packages,
  applies on restart. Must be able to roll back one version.
- Cloud deploys continuously from git via Vercel; Supabase schema changes via
  versioned migrations only — never manual edits in the dashboard.

---

## 9. Observability

- Structured JSON logs on the agent, rotated, capped at 500 MB.
- Agent heartbeat every 60 s → `sites.last_seen`. No heartbeat for 10 min = offline
  in dashboard.
- Agent reports health metrics with the heartbeat: per-camera FPS, detection time,
  CPU/RAM, queue depth, license state, disk usage.
- Cloud error tracking (e.g. Sentry) on API and dashboard.
- **A "diagnostics bundle" export** (logs + config with secrets redacted + last
  benchmark) that a customer can send you in one click. With remote support across
  time zones, this saves hours per incident.

---

## 10. Testing Requirements

| Type | Requirement |
|---|---|
| Unit | Zone point-in-polygon, schedule/open-hours logic, alert rules, cooldown, limit enforcement, license state machine |
| Integration | Agent ↔ cloud sync incl. offline backfill; Stripe webhook → license state → agent resume |
| **Detection accuracy** | Fixed labeled test set of **real store/gas-station footage** (day, night, rain, glare, fisheye). Track precision/recall per release. |
| **False positive** | **Must measure < 1 false alert per site per week before any external sale.** This is the release gate. |
| Soak | 72-hour continuous run, 6 cameras, no leaks, no drift, no crash |
| Chaos | Kill camera mid-run; kill internet mid-run; kill power; move system clock; corrupt cache — all must recover per Section 5 |
| License | Expiry → grace → suspend → renew → auto-resume, tested end-to-end including fully offline |
| Security | RLS cross-tenant read attempts must fail; signed URL expiry enforced |

**Build the labeled test set from day one.** Every real catch and every false
positive from your own 17 sites goes into it. That growing dataset is both your
regression suite and your only realistic moat.

---

## 11. Acceptance Criteria (v1 ships when ALL are true)

1. 6 cameras on one mid-range PC, sustained, within Section 2 targets
2. Alert lands on phone in < 10 s with snapshot; clip retrievable on demand
3. **False positives < 1 per site per week over 14 consecutive days**
4. Survives camera drop, internet drop, and power loss unattended — auto-recovers
5. Full offline operation with correct queue-and-backfill on reconnect
6. License lifecycle verified end-to-end: expiry → 3-day grace → cameras stop →
   payment → **automatic resume with no human action**
7. Encrypted model cannot be loaded without a valid license token
8. Tier limits enforced on both server and agent
9. RLS verified: no cross-tenant data access
10. Installer completes on a clean Windows machine by a non-technical user,
    including ONVIF discovery
11. Deployed and running on ≥ 5 of the founder's own sites for ≥ 30 days

---

## 12. Open Technical Decisions

| Decision | Due |
|---|---|
| Product name (affects package name, domain, code signing cert) | Before Phase 6 |
| Fine-tune YOLOX on own footage, or ship pretrained? | After Phase 1 benchmark on real clips |
| Native app framework (React Native vs Capacitor wrapping the PWA) | After v1 ships |
| Whether to offer a Docker package for technical customers | After 10 external installs |
