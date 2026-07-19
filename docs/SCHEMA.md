# Backend Schema — [PRODUCT NAME TBD]

PostgreSQL / Supabase. Companion to `TRD.md` and `FLOWS.md`.

**Design decisions this schema encodes**
1. **Multi-tenant by `customer_id`** on every business table, enforced by RLS. A
   customer must never read another customer's rows.
2. **Three roles:** `owner` (everything, billing), `manager` (assigned sites only),
   `clerk` (view only, assigned sites, no clips/billing/settings).
3. **Direct sales only** — no reseller layer. Forward-compatible: a future
   `partners` table with `customers.partner_id` adds it without restructuring.
4. **Incident cases** group related events + clips into one record for police and
   insurance.
5. **Clerk owns identity; Supabase owns data.** We store `clerk_user_id`, never
   passwords.
6. `events` and `counts` are the high-volume tables — index and partition for them,
   not for the small ones.

---

## 1. Enums

```sql
create type user_role       as enum ('owner','manager','clerk');
create type tier_name       as enum ('trial','free','single','double','many');
create type license_state   as enum ('trial','active','grace','suspended','revoked');
create type zone_type       as enum ('restricted','monitored','count');
create type object_class    as enum ('person','car','truck','bus','motorcycle','bicycle','box','packet');
create type event_verdict   as enum ('unreviewed','real','false_alarm');
create type incident_status as enum ('open','submitted','closed');
create type command_type    as enum ('fetch_clip','update_config','restart','deactivate');
create type command_status  as enum ('pending','sent','done','failed','expired');
```

## 2. Tenancy, users, roles

```sql
create table customers (
  id                     uuid primary key default gen_random_uuid(),
  clerk_org_id           text unique not null,
  name                   text not null,
  tier                   tier_name not null default 'trial',
  stripe_customer_id     text unique,
  stripe_subscription_id text,
  created_at             timestamptz not null default now()
);

create table app_users (
  id            uuid primary key default gen_random_uuid(),
  clerk_user_id text unique not null,
  email         text not null,
  full_name     text,
  created_at    timestamptz not null default now()
);

-- role within a customer
create table memberships (
  id          uuid primary key default gen_random_uuid(),
  customer_id uuid not null references customers(id) on delete cascade,
  user_id     uuid not null references app_users(id) on delete cascade,
  role        user_role not null,
  created_at  timestamptz not null default now(),
  unique (customer_id, user_id)
);

-- managers and clerks are scoped to specific sites; owners see all
create table membership_sites (
  membership_id uuid not null references memberships(id) on delete cascade,
  site_id       uuid not null references sites(id) on delete cascade,
  primary key (membership_id, site_id)
);
```

**Access rule:** `owner` → all sites of the customer. `manager` / `clerk` → only
sites listed in `membership_sites`. Enforced in RLS (Section 10), not in the UI.

## 3. Sites, cameras, zones, schedule

```sql
create table sites (
  id            uuid primary key default gen_random_uuid(),
  customer_id   uuid not null references customers(id) on delete cascade,
  name          text not null,
  timezone      text not null default 'America/New_York',  -- required: "closed hours" is local
  agent_key     text unique not null,      -- agent auth; rotatable
  agent_version text,
  last_seen     timestamptz,
  health        jsonb,                     -- cpu, ram, disk, fps per camera
  created_at    timestamptz not null default now()
);

create table cameras (
  id           uuid primary key default gen_random_uuid(),
  site_id      uuid not null references sites(id) on delete cascade,
  customer_id  uuid not null references customers(id) on delete cascade,  -- denormalized for RLS
  name         text not null,
  enabled      boolean not null default true,
  is_online    boolean not null default true,
  offline_since timestamptz,
  created_at   timestamptz not null default now()
);
-- NOTE: rtsp_url and credentials NEVER live in the cloud. They stay in the
-- agent's local encrypted config only. The cloud knows a camera exists, not how
-- to reach it. This is a deliberate security boundary.

create table zones (
  id          uuid primary key default gen_random_uuid(),
  camera_id   uuid not null references cameras(id) on delete cascade,
  customer_id uuid not null references customers(id) on delete cascade,
  name        text not null,
  type        zone_type not null,
  polygon     jsonb not null,              -- [[x,y],[x,y],...] in frame pixels
  min_count   integer,                     -- low-stock threshold for count zones
  created_at  timestamptz not null default now()
);

create table lines (
  id          uuid primary key default gen_random_uuid(),
  camera_id   uuid not null references cameras(id) on delete cascade,
  customer_id uuid not null references customers(id) on delete cascade,
  name        text not null,
  points      jsonb not null,              -- [[x1,y1],[x2,y2]]
  direction   text not null default 'both' -- in | out | both
);

create table schedules (
  site_id    uuid primary key references sites(id) on delete cascade,
  hours      jsonb not null,               -- {"mon":["08:00","22:00"], ...} local time
  updated_at timestamptz not null default now()
);
```

## 4. Events, counts, media (the high-volume tables)

```sql
create table events (
  id            uuid primary key default gen_random_uuid(),
  customer_id   uuid not null references customers(id) on delete cascade,
  site_id       uuid not null references sites(id) on delete cascade,
  camera_id     uuid not null references cameras(id) on delete cascade,
  zone_id       uuid references zones(id) on delete set null,
  ts            timestamptz not null,          -- when it happened (agent clock, UTC)
  object_class  object_class not null,
  confidence    real not null,
  alerted       boolean not null default false, -- did it fire a push?
  during_closed boolean not null default false,
  snapshot_path text,                           -- Supabase Storage key
  clip_local    boolean not null default false, -- agent holds a clip for this
  clip_path     text,                           -- set once uploaded on demand
  verdict       event_verdict not null default 'unreviewed',
  verdict_by    uuid references app_users(id),
  verdict_at    timestamptz,
  agent_event_id text,                          -- agent's local id
  created_at    timestamptz not null default now(),
  unique (site_id, agent_event_id)               -- IDEMPOTENT SYNC: retries can't duplicate
) partition by range (ts);

-- monthly partitions; drop old partitions instead of DELETE (instant, no bloat)
create table events_2026_07 partition of events
  for values from ('2026-07-01') to ('2026-08-01');

create index on events (customer_id, ts desc);
create index on events (site_id, ts desc);
create index on events (zone_id, ts desc) where alerted = true;
create index on events (customer_id, verdict) where verdict = 'unreviewed';
```

```sql
create table counts (
  id             uuid primary key default gen_random_uuid(),
  customer_id    uuid not null references customers(id) on delete cascade,
  site_id        uuid not null references sites(id) on delete cascade,
  camera_id      uuid not null references cameras(id) on delete cascade,
  zone_id        uuid references zones(id) on delete cascade,
  line_id        uuid references lines(id) on delete cascade,
  ts             timestamptz not null,
  object_class   object_class not null,
  count          integer not null,
  agent_count_id text,
  unique (site_id, agent_count_id)
) partition by range (ts);

create index on counts (customer_id, ts desc);
create index on counts (site_id, object_class, ts desc);
```

**Reports read from a rollup, never from raw rows:**

```sql
create materialized view daily_rollup as
select customer_id, site_id, date_trunc('day', ts) as day,
       count(*) filter (where alerted) as alerts,
       count(*) filter (where alerted and during_closed) as after_hours_alerts,
       count(*) filter (where object_class = 'person') as person_events,
       count(*) filter (where object_class in ('car','truck','bus')) as vehicle_events
from events group by 1,2,3;

create unique index on daily_rollup (customer_id, site_id, day);
-- refresh concurrently, hourly, via pg_cron
```

## 5. Incident cases (police / insurance)

```sql
create table incidents (
  id            uuid primary key default gen_random_uuid(),
  customer_id   uuid not null references customers(id) on delete cascade,
  site_id       uuid not null references sites(id) on delete cascade,
  case_number   text not null,             -- human-readable: MAIN-2026-0007
  title         text not null,
  description   text,
  occurred_at   timestamptz not null,
  status        incident_status not null default 'open',
  estimated_loss numeric(10,2),
  police_report_ref text,
  created_by    uuid references app_users(id),
  created_at    timestamptz not null default now(),
  unique (customer_id, case_number)
);

create table incident_events (
  incident_id uuid not null references incidents(id) on delete cascade,
  event_id    uuid not null,
  event_ts    timestamptz not null,        -- needed to reference the partitioned table
  note        text,
  primary key (incident_id, event_id)
);

create table incident_notes (
  id          uuid primary key default gen_random_uuid(),
  incident_id uuid not null references incidents(id) on delete cascade,
  author_id   uuid references app_users(id),
  body        text not null,
  created_at  timestamptz not null default now()
);
```

**Retention rule that matters:** events attached to an incident are **exempt from
tier-based deletion**. Evidence must survive the 30/90/365-day window — losing a clip
a customer needs for a police report is a product failure and a legal problem.

## 6. Licensing, trials, devices

```sql
create table licenses (
  id                uuid primary key default gen_random_uuid(),
  customer_id       uuid not null references customers(id) on delete cascade,
  site_id           uuid unique references sites(id) on delete cascade,
  license_key       text unique not null,           -- STOREV-XXXX-XXXX-XXXX-XXXX
  state             license_state not null default 'trial',
  expires_at        timestamptz not null,
  device_fingerprint text,
  activated_at      timestamptz,
  max_cameras       integer not null default 2,
  reactivations     integer not null default 0,     -- cap ~3 per 90 days
  last_validated_at timestamptz,
  created_at        timestamptz not null default now()
);

create index on licenses (state, expires_at);   -- drives the expiry sweep job

create table license_events (
  id         bigserial primary key,
  license_id uuid not null references licenses(id) on delete cascade,
  ts         timestamptz not null default now(),
  old_state  license_state,
  new_state  license_state not null,
  reason     text                                  -- 'stripe_paid','expired_3d','manual_revoke'
);

-- GLOBAL, not per-customer: this is the anti-abuse table
create table trial_registry (
  fingerprint  text primary key,
  first_seen   timestamptz not null default now(),
  ip_hash      text,
  email        text,
  customer_id  uuid references customers(id) on delete set null
);
create index on trial_registry (ip_hash);
create index on trial_registry (email);
```

**Why `trial_registry` is global:** a reinstall on the same machine must not grant a
second trial. Deleting a customer must not erase the fingerprint record — hence
`on delete set null`, not cascade.

## 7. Agent command queue (clip fetch, config push)

```sql
create table agent_commands (
  id           uuid primary key default gen_random_uuid(),
  site_id      uuid not null references sites(id) on delete cascade,
  customer_id  uuid not null references customers(id) on delete cascade,
  type         command_type not null,
  payload      jsonb not null default '{}',   -- {event_id, from_ts, to_ts}
  status       command_status not null default 'pending',
  requested_by uuid references app_users(id),
  created_at   timestamptz not null default now(),
  sent_at      timestamptz,
  completed_at timestamptz,
  error        text
);
create index on agent_commands (site_id, status) where status = 'pending';
```

The agent polls this on each heartbeat. Commands expire after 24h so an offline site
doesn't accumulate stale work.

## 8. Notifications, announcements, audit

```sql
create table push_tokens (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references app_users(id) on delete cascade,
  token      text unique not null,
  platform   text not null,                       -- web | ios | android
  last_used  timestamptz,
  created_at timestamptz not null default now()
);

create table notification_prefs (
  user_id      uuid not null references app_users(id) on delete cascade,
  site_id      uuid not null references sites(id) on delete cascade,
  zone_ids     uuid[],                             -- null = all zones
  quiet_hours  jsonb,
  email_enabled boolean not null default true,     -- fallback is on by default
  push_enabled  boolean not null default true,
  primary key (user_id, site_id)
);

create table announcements (
  id          uuid primary key default gen_random_uuid(),
  customer_id uuid not null references customers(id) on delete cascade,
  site_id     uuid references sites(id) on delete cascade,   -- null = all sites
  author_id   uuid references app_users(id),
  body        text not null,
  created_at  timestamptz not null default now()
);

create table audit_log (
  id          bigserial primary key,
  customer_id uuid references customers(id) on delete set null,
  actor_id    uuid references app_users(id),
  action      text not null,     -- 'license.revoked','device.deactivated','user.invited'
  target      text,
  metadata    jsonb,
  ip_hash     text,
  ts          timestamptz not null default now()
);
```

## 9. Retention job (also cost control)

```sql
-- pg_cron, nightly
-- 1. drop event/count partitions older than the customer's tier window
-- 2. delete Storage objects for deleted rows
-- 3. NEVER delete events referenced by incident_events
-- 4. expire agent_commands older than 24h
-- 5. refresh daily_rollup
```

## 10. Row Level Security (enable on EVERY table)

```sql
alter table events enable row level security;

-- helper: which sites can the current Clerk user see?
create or replace function visible_site_ids() returns setof uuid
language sql stable security definer as $$
  select s.id
  from memberships m
  join app_users u  on u.id = m.user_id
  join sites s      on s.customer_id = m.customer_id
  left join membership_sites ms
         on ms.membership_id = m.id and ms.site_id = s.id
  where u.clerk_user_id = auth.jwt() ->> 'sub'
    and (m.role = 'owner' or ms.site_id is not null);
$$;

create policy events_read on events for select
  using (site_id in (select visible_site_ids()));

-- clerks are read-only: no insert/update/delete policies granted to them
create policy events_verdict_update on events for update
  using (
    site_id in (select visible_site_ids())
    and exists (
      select 1 from memberships m join app_users u on u.id = m.user_id
      where u.clerk_user_id = auth.jwt() ->> 'sub'
        and m.customer_id = events.customer_id
        and m.role in ('owner','manager')
    )
  );
```

Repeat the read policy pattern for every tenant table. **Agents do not use RLS** —
they authenticate with `agent_key` against Edge Functions using the service role, and
those functions scope writes to that key's `site_id`.

## 11. Rules for whoever builds this

1. **Never store camera credentials or RTSP URLs in the cloud.** Agent-local,
   OS-keystore-encrypted, only.
2. **Idempotent sync.** `unique (site_id, agent_event_id)` — a retried batch after a
   dropped connection must not duplicate events.
3. **Denormalize `customer_id` onto child tables.** It makes every RLS policy a single
   index lookup instead of a multi-table join on your hottest queries.
4. **Store timestamps as `timestamptz` in UTC; store `sites.timezone` separately.**
   "After hours" is a local-time question across 6 states — getting this wrong
   silently breaks your core alert rule.
5. **Partition `events` and `counts` by month.** Dropping a partition is instant;
   `DELETE` on millions of rows is not.
6. **Reports read `daily_rollup`, never raw events.**
7. **Migrations only** — never edit schema by hand in the Supabase UI.
8. **Incident-linked events are never auto-deleted.**
