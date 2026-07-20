# UI/UX & Design Brief — [PRODUCT NAME TBD]

Companion to `PRD.md`, `SPEC.md`, `TRD.md`, `FLOWS.md`.

---

## 1. The strategic call: what to take from Spot AI, and what to reject

Spot AI's site is well built — worth studying. But copy it wholesale and you will
**actively damage your positioning.** Their design sells to enterprise buyers; yours
sells to a man who owns four gas stations.

### Take these (they work for anyone)
- **Video-first hero.** Their homepage leads with looping footage of the product
  working, not a stock illustration. For a camera product this is right — show, don't
  describe.
- **"Keep your cameras."** They answer it in the FAQ directly: camera-agnostic, no
  rip-and-replace. Make this louder than they do — it's more central to you.
- **Named customers + real quotes.** Their testimonials are attributed to real people
  at real companies, including a fuel company. Attribution is what makes proof land.
- **Hard numbers as a section.** They state customer counts and comparisons plainly.
- **Self-serve trial hook.** They offer an instant "drop in a video, no install, no
  sales call" demo. That instinct — let people try before talking to anyone — is
  exactly your model, and you should go further with it.

### Reject these (they are enterprise signals that hurt you)
| Spot AI does | Why you must not |
|---|---|
| "Request a Demo" as the primary CTA everywhere | Your entire wedge is self-serve. Your CTA is **"Download free trial."** A demo request says "expensive, call sales." |
| No pricing shown at all | **Publish your prices.** This is your single sharpest differentiator against every funded competitor. |
| "AI agents," "digital force multiplier," "Cambrian moment" | A gas station owner does not talk like this. It reads as expensive and abstract. |
| Dark futuristic gradients + abstract AI visuals | Signals "enterprise SaaS, six-figure contract." You need "affordable, real, works tonight." |
| Compliance badge wall (SOC 2, NDAA, HIPAA) | Meaningless to your buyer. Yours is **"no facial recognition — we watch actions, not faces."** |

**The one-line positioning your whole design must serve:**
> Your cameras already record theft. Now they'll tell you while it's happening.

---

## 2. Design direction: "The 3AM Forecourt"

Grounded in the subject's actual world — a fuel canopy at 3am. Sodium-amber light
pooling on wet concrete, everything else in deep blue-black. That is literally when
and where your product earns its money, and it gives a palette nobody else in this
category is using (competitors all sit in cool blue/violet "AI tech" territory).

### 2.1 Color tokens

```
--night        #0B0F14   deep blue-black    canopy dark, primary background
--asphalt      #151C24   raised surface     cards, panels
--concrete     #232D38   borders, dividers, inactive
--sodium       #FFB347   AMBER — the signature. alerts, primary action, focus
--sodium-dim   #7A5520   amber at rest: badges, timeline marks
--allclear     #4ADE80   green — armed, online, healthy, "no incidents"
--critical     #FF5C4D   red — suspended license, camera offline, confirmed theft
--paper        #F5F7FA   primary text on dark
--muted        #8A97A6   secondary text, labels, timestamps
```

**Light mode for the marketing site** (`--paper` background, `--night` text, amber
accent) — a shop owner researching on his phone in daylight should not get a dark
site. **Dark mode for the dashboard and app** — it's a monitoring tool, often viewed
at night, and dark makes camera snapshots read correctly instead of glowing.

Amber is used with discipline: it is the alert color, so it must never appear as
decoration. If amber is on screen, something needs attention or is the one action to
take.

### 2.2 Typography

| Role | Face | Why |
|---|---|---|
| Display | **Archivo** (600/700, tight tracking) | Industrial grotesque with signage DNA — reads like forecourt and price-board lettering, not another SaaS geometric sans |
| Body / UI | **IBM Plex Sans** (400/500) | Engineered, highly legible at small sizes, slightly technical without being cold |
| Data | **IBM Plex Mono** (400) | **Functional, not stylistic**: timestamps, camera IDs, license keys, counts. Aligned columns of numbers are core to this product |

Type scale (dashboard): 12 / 14 / 16 / 20 / 28 / 40. Display sizes only on marketing.

### 2.3 Layout & form

- 8px spacing grid. Radius 6px on controls, 10px on cards. **No pill shapes** — this
  is equipment software, not a consumer app.
- 1px `--concrete` borders instead of shadows on dark surfaces.
- Density: **comfortable, not cramped.** Your user is 50, on a phone, in a store, at
  night. Minimum body text 14px, tap targets ≥ 44px.
- Motion: minimal. One purposeful moment — a new alert slides in and pulses amber
  once. Everything else is instant. Respect `prefers-reduced-motion`.

### 2.4 Signature element: the Night Ribbon

Each site gets a horizontal 24-hour strip. Closed hours render as a darker band,
open hours lighter; each alert appears as an amber tick at its actual time; camera
downtime shows as a red gap in the ribbon.

Why it earns its place: an owner sees a week of ribbons stacked and instantly reads
his own pattern — "every incident is between 1am and 4am, and camera 3 keeps dying."
It encodes real information rather than decorating, and it's the thing people will
remember and screenshot.

### 2.5 Detection box colors (overlay rendering)

**The principle: color encodes meaning first, class second.** A person in the
aisle at 2pm and a person in the stockroom at 2am are identical to the model but
opposite to the owner. The box has to show that instantly — so **class color is
the default, and alert state overrides it.**

**Class colors (a normal, non-alerting detection):**

| Class | Token | Color | Why this color |
|---|---|---|---|
| person | `--det-person` | `#4EA8FF` clear blue | Reads against both night-IR grey and daylight |
| vehicle | `--det-vehicle` | `#A78BFA` violet | Distinct from person at a glance |
| bag | `--det-bag` | `#F472B6` pink | Kept separate — it's concealment *context*, not a subject |
| inventory | `--det-inventory` | `#2DD4BF` teal | Operational, not threatening |
| low-confidence | `--det-weak` | `#6B7280` grey | 1px, **no label**; visible for debugging, invisible in feel |

**Alert state overrides all of it.** The moment a detection fires an alert, its
box becomes **sodium amber `#FFB347`** with a **thicker stroke** and the **zone
name in the label**. Amber is the alert color across the entire product, so it
**must never appear on a normal detection** — the instant it decorates, it stops
meaning anything.

**Red `#FF5C4D` is reserved** for events a human has confirmed as real theft
(verdict = `real`). Never used for a live/unreviewed detection.

```
draw priority (highest wins):
  confirmed theft   → red    #FF5C4D, thick, label = case #
  alerting          → amber  #FFB347, thick, label = zone name
  normal detection  → class color above, 2px, label = class
  low-confidence    → grey   #6B7280, 1px, no label
```

---

## 3. Website (marketing)

Structure — one page does most of the work:

```
NAV        logo · Product · Pricing · Docs · [Log in] · [Start free trial]  ← amber
HERO       H1: "Your cameras already record theft.
               Now they'll tell you while it's happening."
           Sub: Works with the cameras you already own. 7-day free trial.
           [Download free trial]  [See pricing]
           → BACKGROUND: looping real detection footage (blurred/neutral),
             boxes tracking a person, amber alert card sliding in
PROOF      Three plain numbers: alert speed · cameras supported · sites protected
PROBLEM    "You find out the next morning." The gap between recording and knowing.
HOW        Three steps, honestly boring: 1 Install  2 Find your cameras
           3 Get alerts. Screenshot each. No jargon.
WORKS WITH Camera brand logos: Dahua · Hikvision · Amcrest · Lorex · Reolink ·
           Uniview · "and any ONVIF camera or NVR"
PRICING    ★ FULL TABLE ON THE PAGE. Real numbers. Not "contact sales."
PRIVACY    "No facial recognition. Video stays in your store." Short, plain.
FAQ        Does it work with my cameras? What if my internet drops? Do I need
           new hardware? What happens when the trial ends?
CTA        [Download free trial] — no email gate before download
FOOTER     minimal
```

**Pages:** `/` `/pricing` `/download` `/buy` `/renew` `/dashboard` `/docs` `/support`
`/privacy` `/terms`

**Hard rules**
- Primary CTA is always **"Start free trial"** or **"Download"** — never "Request a demo."
- Pricing is public and above the fold on `/pricing`.
- Every claim is concrete. Not "AI-powered intelligence" but "Alert on your phone in
  under 10 seconds."
- The word "agent" never appears in customer-facing copy. It's the software.

---

## 4. Dashboard UI

```
┌─ SIDEBAR ──┬─ MAIN ─────────────────────────────────────────────┐
│ ◆ Sites    │  Sites                          [+ Add site]       │
│   Events   │  ┌──────────────────────────────────────────────┐  │
│   Reports  │  │ ● Main Street        4 cameras   2 alerts     │  │
│   Board    │  │ ▁▁▂▁▁▁█▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁  ← Night Ribbon      │  │
│   Search   │  ├──────────────────────────────────────────────┤  │
│ ─────────  │  │ ● Highway 6          6 cameras   0 alerts     │  │
│   Billing  │  │ ▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁                     │  │
│   License  │  ├──────────────────────────────────────────────┤  │
│   Settings │  │ ○ Oak & 5th   OFFLINE 12m       ⚠            │  │
└────────────┴──────────────────────────────────────────────────┘
```

- **Sites overview is home.** Green dot = armed and healthy. The absence of amber is
  the good state — an owner should be able to glance and feel fine.
- **Event card** = snapshot thumbnail left, then zone · camera · time in mono, then
  two buttons: `Get clip` and `Real / False alarm`.
- **Event detail**: large snapshot, metadata in mono, `Get clip` (states: request →
  fetching → play; if the site is offline say "Available when Oak & 5th reconnects" —
  never a dead button).
- **Empty states are instructions, not decoration.** No events yet → "No alerts yet.
  That's the goal. Your cameras are watching — you'll hear from us when something
  happens."
- **Camera offline is styled as a security warning, not a technical notice.** A
  disabled camera is how theft gets hidden. Red, prominent, with a plain fix step.

## 5. Installer / agent UI

Ten minutes, non-technical, no phone call. Full-screen wizard, one decision per step,
progress visible, `Back` always available.

- **System check** shows a plain verdict: "This PC can handle 6 cameras" or "This PC
  can handle 3 cameras. Add a graphics card for more." Never raw benchmark numbers.
- **Camera discovery** runs automatically and shows found cameras as they appear.
  Manual RTSP entry exists but is a small secondary link — most people should never
  see it.
- **Zone drawing** is on a live frame, drag to draw, name it, pick a type in plain
  words: *"Alert any time"* / *"Alert only when closed"* / *"Just count things here."*
  Never the words restricted/monitored/count on screen.
- **Final step sends a real test alert** and does not let you finish until the user
  confirms they got it. This is the highest-leverage screen in the whole product.

## 6. Mobile alert (the moment that matters most)

The push notification is your product for 95% of your customer's experience.

```
  ┌────────────────────────────────┐
  │ ⬤ Main Street · Stockroom      │
  │                                │
  │      [ snapshot, box drawn ]   │
  │                                │
  │ Person detected · 2:14 AM      │
  │ Store closed                   │
  │  [ Get clip ]  [ False alarm ] │
  └────────────────────────────────┘
```

Site and zone first (an owner with 6 sites needs to know *where* before *what*).
Snapshot large. Time and closed/open state in mono. Two actions, no more.

## 7. Copy rules

- Say what happened, in his words: "Person in the stockroom at 2:14 AM." Not
  "Anomalous detection event triggered."
- Buttons name the outcome: `Get clip`, `Renew`, `Deactivate device`. Never `Submit`.
- Errors state the fix: "Camera 3 stopped responding. Check that it has power and is
  on the same network." Never "Error: stream unavailable."
- Trial/expiry copy is direct and unembarrassed: "Your trial ends in 2 days. Cameras
  stop watching after that." No guilt, no exclamation marks.
- Banned words: agent, leverage, empower, seamless, revolutionize, unlock, robust.

## 8. Quality floor (non-negotiable)

Mobile-first (owners live on phones) · tap targets ≥ 44px · visible keyboard focus in
amber · WCAG AA contrast — verify `--sodium` on `--night` and darken text-on-amber to
`--night` · `prefers-reduced-motion` respected · works one-handed · dashboard usable
on a 5-year-old Android in a store with bad signal.
