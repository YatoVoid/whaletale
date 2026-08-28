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

<!--
Later milestones (planned):
M2 schema + attribution · M3 report · M4 edge agent · M5 cloud API + sync
M6 operator console · M7 onboarding · M8 fleet admin · M9 billing · M10 hardening
-->
