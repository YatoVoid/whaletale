# Changelog

One entry per milestone from the project spec, Section 14.

## [Unreleased]

### M10: Hardening
- `docs/edge-cases.md`: full spec §8 coverage matrix (done / partial / deferred,
  each row citing the test that pins it, plus a tracked list of the eight
  deferred refinements and their build notes).
- Edge: re-entry grace window (spec 8.2). An occluded person reappearing under a
  new track id no longer counts as a second entry; a dropped track is parked for
  `EDGE_REENTRY_SECONDS` and a new track within `EDGE_REENTRY_DISTANCE` inherits
  its visit. `ZoneStats.reentries_merged` counts hits.
- Cloud: optimistic locking on zone reshape (spec 8.4). `ReshapeIn.base_version_id`
  is checked against the open primary; `GET /v1/spaces/{id}/zone-versions/current`
  returns the id and polygon to edit from. Concurrent reshape returns 409.
- Cloud: security headers on every API response (HSTS, nosniff, frame-deny,
  no-referrer, `default-src 'none'` CSP).
- Web: the zone editor loads the current polygon and version instead of starting
  blank, and surfaces the reshape conflict.
- Test: bucket timestamps are stored verbatim, the cloud never re-stamps (spec 8.4).
- Cloud: `LoginThrottle` locks a client IP out after 10 failed auth attempts in
  15 minutes, on the ingest, operator, and admin auth paths. A success clears
  the key.
- Cloud: `security_event()` writes one structured line to the `whaletale.security`
  logger for every auth failure, permission denial, rate-limit hit, and admin
  action, so they can be shipped somewhere queryable.
- Edge + cloud: camera-drift detection (spec 8.1). `calibration.py` hashes the
  live view (dHash) against an on-box reference; a fixed camera that gets bumped
  or re-aimed diverges past `EDGE_DRIFT_HAMMING_THRESHOLD` bits over
  `EDGE_DRIFT_SAMPLES` hourly checks, at which point the pipeline stops counting
  it and reports `needs_recalibration` in the heartbeat. The cloud raises a
  customer `camera_moved` alert. `whaletale-agent --recalibrate` re-captures the
  references after a deliberate move. Reference hashes never leave the box.
- Cloud + web: overlapping-zone confirmation (spec 8.3). `find_zone_overlaps`
  checks a proposed polygon against every other open primary zone on the same
  camera; `reshape_zone` returns 409 `zone_overlap` listing the spaces unless
  they are in a parent/child relation with the edited space or the caller sets
  `acknowledge_overlap`. `ApiError` now carries the parsed `detail`; the zone
  editor renders the warning and a "Save with the overlap" action.
- Edge: per-camera health telemetry (spec 8.1 / 9). The agent tracks a rolling
  mean detection confidence, actual fps, last-frame time, and online/offline/
  frozen status per camera, writes them to a local `camera_health` table, and
  the sync client ships them in the heartbeat `per_camera` block. The cloud
  fleet view already derives the confidence-drop alert from this.
- Edge: frozen-stream detection (spec 8.1). `decode.FrozenFrameDetector` flags a
  source that keeps delivering byte-identical frames for longer than
  `EDGE_FROZEN_FRAME_SECONDS` (default 30); the camera worker then reports a
  `frozen frame` error like a decode failure. The clock-drift item is marked
  not-applicable: the agent stamps frames with the box clock, never the
  camera's, so a drifted camera clock never reaches a bucket.

### M1: Prove the pipeline
- Repository scaffold: layout, `.gitignore`, `.env.example`, pre-commit hooks,
  CI (lint, type-check, tests, secret scan, license audit), branch protection.
- Edge pipeline proof: PyAV decode, RT-DETR person detection, Norfair tracking,
  one hard-coded normalized polygon, entry counting with dwell threshold and
  enter/exit hysteresis, console output, FPS measurement. No DB, no UI.
- Edge hardening: config and CLI arg validation with messages that name the bad
  value and run before the model download; RTSP/webcam reconnect with capped
  backoff while a file decode error stays fatal; zone-rectangle bounds checks;
  tests for decode decimation, reconnect give-up, and the new failure paths.

### M6: Operator console (backend)
- Operator REST API (`whaletale_cloud/api/operator/`): sites, spaces list with
  current occupant, space detail (metrics + occupancy), occupants CRUD, the
  schedule grid (spec 10.3, vacancy is a state not a blank), overview ranked by
  capture rate with vacancies and box/camera health, and the per-space report
  PDF.
- Writes: create tenancy with conflict detection naming both tenancies (spec
  8.3), delete tenancy (retroactive edit recomputes on the join), zone reshape
  that closes the current version and inserts a new one with a "creates version
  N" message (spec 5.2.2).
- Auth: hashed bearer token per `operator_user`, every query scoped to the
  user's sites (`operator_user_sites`); Alembic migration. Real Auth.js login
  and the Next.js screens are the remaining M6 work.
- `whaletale_cloud/schedule.py`: per-day occupant resolution reusing the
  attribution tenancy rules.

### M9: Billing
- `whaletale_cloud/billing.py`: Stripe subscription per site, quantity = the
  live `cameras` count recomputed server-side (never a client-sent price or
  quantity). `preview_change` (the spec 8.5 change-preview), `apply_change`
  (adds prorate now, removes defer to the next period), `handle_webhook`
  (signature-verified: payment failed -> grace window -> read-only; paid ->
  active; deleted -> cancel + export window).
- `subscriptions` table + migration; `StripeGateway` protocol so tests inject a
  fake.
- Operator API: `GET/preview/apply .../billing`; `POST /webhooks/stripe`.
  Operator writes return 402 once the grace window elapses; ingest and
  heartbeats are never gated (spec 8.5, tested).
- Console Settings: a billing panel with the preview -> confirm flow.

### M8: Fleet admin + alerts
- `whaletale_cloud/fleet.py`: derives per-site health and the spec-9 alert
  conditions from heartbeats — camera dark > 1h (customer-facing, plain
  language), sync stale > 6h, disk < 20%, mean confidence down > 30% from a
  trailing baseline, agent version behind. `sync_alerts` upserts one open
  `alerts` row per condition and resolves those that clear.
- `heartbeat` gains `disk_total_bytes` (wire + edge + column) so the disk ratio
  is real; `alerts` table + migration.
- `/admin/*` API (staff token `WHALETALE_ADMIN_TOKEN`): `GET /admin/fleet`,
  `POST /admin/fleet/evaluate`, `GET /admin/alerts`. Sentry wired via
  `SENTRY_DSN`, inert otherwise.
- Still open: the admin console UI (staff-only, separate from the operator app).

### M7: Onboarding
- `edge/onboarding/`: WS-Discovery camera probe (manufacturer / model / IP from
  ONVIF scopes), the five-check validation gate (opens < 10s, resolution
  >= 640x480, decode >= 2 fps, test inference < 200ms, >= 1 clean frame), and
  Fernet-sealed RTSP credentials keyed from `WHALETALE_SITE_SECRET` (plaintext
  never reaches the cloud, never logged).
- `whaletale-onboard` CLI: `--discover`, or `--source URL --name ... --emit` to
  print a validated `site.json` camera block.
- Cloud operator API: pair an edge box (token returned once, stored as SHA-256),
  list/revoke boxes, register and list validated cameras.
- Console Settings: pair a box, add a camera.
- Still open: the first-run wizard flow and the zone editor's live detection
  overlay (needs a frame+detections endpoint from the box).

### M6: Operator console (frontend, in progress)
- `web/`: Next.js App Router + TypeScript scaffold. Visual world is a "working
  drawing set" — flat ink on paper, hairline rules, the grid as structure
  (`DESIGN.md`), self-hosted IBM Plex, light only. Auth.js sign-in (email +
  operator token for now).
- Screens: Overview (site health, spaces ranked by capture rate with this-week
  vs prior-week deltas, vacancies), Schedule (spaces×days grid, block select,
  side-panel assignment with permanent / weekly / one-off forms and conflict
  surfacing), Space detail (metrics with definition links + units + period,
  occupancy timeline, report PDF), Spaces list, Occupants (list + add).
  Vacancy, anomalous, and degraded each render as a distinct state.
- `web` CI job (typecheck, lint, vitest, build) and branch-protection check.
- Still to come: zone editor, Reports, Settings screens.

### M5: Cloud API + sync
- `shared/schemas/wire.py`: the edge <-> cloud sync contract (`IngestRequest`,
  `HeartbeatRequest`, ...), separate from the persisted-row models so a payload
  version can lag the DB schema (spec 5.3). Dropped `bucket_end` from
  `site_totals` to match Section 5.1.
- FastAPI ingest API (`whaletale_cloud/api/`, `whaletale-api`): `POST /v1/ingest`
  idempotent upsert of observations and site totals onto the M2 schema (spec
  8.4), `POST /v1/heartbeat` storing Section 9 telemetry in new `edge_boxes` /
  `heartbeats` tables (Alembic migration).
- Pairing-token auth (SHA-256 at rest), payload `site_id` must match the token's
  site, `zone_version_id`s must belong to that site, 8 MB body cap, per-token
  rate limit, auth-failure logging. No CORS (machine-to-machine), no docs route.
- Contract tests pin the exact edge payload shape against the wire schema.

### M4: Edge agent
- Bucket stats reconciled to the Section 5.1 `observations` columns: `exits`
  (clean boundary crossings), `peak_occupancy` (max concurrent in the bucket),
  `capture_events` (= entries on the edge).
- `agent/store.py`: local SQLite buffer for 15-minute rollups. WAL, integrity
  check on open, upsert on `(zone_version_id, bucket_start)`, `synced_at IS NULL`
  as the sync watermark, `prune_synced` rotation (spec 8.4).
- `WallClockAggregator`: buckets aligned to real 15-minute wall-clock windows,
  each finished bucket handed to the store.
- `agent/detect.py`: `detect_batch` - one processor call and one model forward
  for frames batched across every stream (spec 6.2 step 2).
- `agent/siteconfig.py`: the git-ignored per-box `site.json` (cameras, sources,
  zone polygons with cloud `zone_version_id`s), validated on load.
- `agent/pipeline.py` + `whaletale-agent`: one decode thread per camera, one
  batched inference per tick, per-zone tracking and aggregation into the store,
  per-bucket `site_totals`. One dead camera does not stop the others.
- `sync/` + `whaletale-sync`: watermark push (idempotent, resumable, buffers
  through a WAN outage) and a Section 9 heartbeat. No third-party HTTP dep.
- `edge/deploy/`: systemd units for the agent and sync services.

### M4 (early, ahead of sequence): edge attribution + rollup buckets
- Edge attribution: zone catchment (polygon dilated by `catchment_frac`),
  passerby tracking (a track that reaches the catchment but never the zone
  polygon), capture rate `entries / (entries + passersby)`, and person-seconds
  (sum over people of time inside, distinct from occupied seconds), printed in
  the run summary.
- Edge rollup buckets: the run is split into fixed stream-time buckets
  (`bucket_seconds`, default 900) with continuous track identity across
  boundaries. Time metrics split at the boundary, event metrics land in the
  bucket they resolve in. The summary prints a per-bucket table plus run
  totals.

### M2: Schema + attribution
- Cloud scaffold: `cloud/` uv package, `shared/schemas/` as the single source of
  truth, SQLAlchemy 2.0 engine/session, `pydantic-settings` config, local
  `docker/compose.cloud.yml` (Postgres + Redis), CI `cloud` job (ruff, mypy,
  `alembic upgrade` + autogenerate check, pytest against a Postgres service),
  license audit extended to cloud deps.
- Section 5.1 schema: Pydantic v2 models and matching SQLAlchemy ORM for all
  nine tables, with 5.2 invariants enforced as constraints (no occupant column
  on observations; one open primary zone version per space; append-only
  geometry; UTC timestamps; upsert key on `(zone_version_id, bucket_start)`).
  Alembic baseline migration, round-trips down/up.
- Synthetic demo-site seed: reshaped zone, failover version, permanent /
  recurring (RRULE) / one_off tenancies, a vacancy gap, a never-leased space, a
  festival day and a closure day. Deterministic.
- Attribution join: occupant (or vacant) per observation bucket, resolved
  against the zone version effective then, with non-primary failover marked
  `degraded`; `closure` annotations suppress tenancy; retroactive edits and
  occupant renames flow through because it is a query-time join.
- Metrics (6.4) and normalization (6.5) as tested Python: capture rate, traffic
  share, occupied seconds, estimated period dwell; share-of-site, trailing
  same-weekday baseline with DST-correct shifting and `exclude_from_baseline`
  respected, >2 SD anomaly flag, peer-zone capture-rate rank.
- Save-time checks (8.3): self-intersecting / out-of-frame polygons, and
  tenancy conflicts (date and daily-window overlap).

### M3: Report
- The Section 11 one-pager for a space over a period, HTML and PDF (WeasyPrint,
  Jinja2), with server-rendered SVG charts. `whaletale-report` generates it from
  the seeded demo site.
- Report data (`report.py`): headline metrics + peer rank, hourly and daily
  entry pattern, per-day occupancy timeline (missing days read as vacant), and a
  per-day anomaly table joined to `day_annotations` (spec 6.5).
- `license_audit.py` now clears a disjunctively-licensed dependency (GPL arm
  beside an LGPL or permissive arm), for `pyphen` via WeasyPrint.

<!--
Later milestones (planned):
M2 schema + attribution · M3 report · M4 edge agent · M5 cloud API + sync
M6 operator console · M7 onboarding · M8 fleet admin · M9 billing · M10 hardening
-->
