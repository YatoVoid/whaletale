# Changelog

One entry per milestone from the project spec, Section 14.

## [Unreleased]

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
