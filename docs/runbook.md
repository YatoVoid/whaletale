# Runbook

What to do when a site alerts. One section per milestone on how that milestone
fails and the response.

## M1: pipeline proof

Local dev only, no deployment, no alerts. Failure modes seen while running
`whaletale-edge`:

| Symptom | Cause | Action |
|---|---|---|
| `error: cannot open source ...` | Bad path, wrong RTSP creds, camera unreachable | Verify the source plays in `ffplay`. For RTSP, check credentials and that the box can route to the camera. |
| Run pauses then prints reconnect, or exits with `giving up on ... after N reconnect attempts` | Live RTSP/webcam stream dropped | Transient drops are retried with backoff (5 attempts). A file that fails mid-decode is fatal by design. Persistent failure means the camera is down or the network path is broken. |
| `error: --zone: ...` or `error: EDGE_* ...` before the model loads | Bad CLI arg or env value | The message names the offending value. Cheap checks run before the model download so a typo costs nothing. |
| First run hangs for minutes | RT-DETR weights downloading to `EDGE_HF_CACHE` | Wait once; cached afterwards. Pre-warm with `uv run whaletale-edge --warm`. |
| Achievable FPS well below `--fps` on CPU | RT-DETR PyTorch on a CPU-only box measured ~0.2 fps (`r50vd`) / ~0.5 fps (`r18vd`) single stream | Expected for the proof. M4 exports to ONNX/TensorRT and batches across cameras; the reference edge box has an RTX 3060. Use `--model PekingU/rtdetr_r18vd` for faster iteration. |
| Entry count looks inflated | Track ID churn from occlusion; no re-entry grace window yet | Known M1 limitation. Re-entry merge (spec 8.2) lands in M4. |
| Zero entries but people are visible | Polygon doesn't cover where people walk | Adjust the normalized points in `edge/agent/zones.py`. Live overlay editor is M6. |

## M2: schema and attribution

Cloud schema, seed, and the attribution/metrics/normalization logic. No
deployment, no live sync yet (that is M5). Failure modes while developing:

| Symptom | Cause | Action |
|---|---|---|
| `alembic check` fails in CI with a diff | A model was changed without generating a migration | `cd cloud && uv run alembic revision --autogenerate -m "..."`, review the file, `ruff format` it, commit. |
| Tests error with `could not connect` / `Connection refused` | No Postgres | `docker compose -f docker/compose.cloud.yml up -d`, or set `WHALETALE_TEST_DATABASE_URL`. Without either, tests start a throwaway container and need Docker. |
| Attribution shows a bucket as `VACANT` unexpectedly | No tenancy covers that bucket, or a recurring tenancy's RRULE / daily window excludes it, or a `closure` day annotation suppressed it | Check `tenancies` for the space and the `day_annotations` for that date. Vacancy is real information, not an error (spec 8.3). |
| A report period looks wrong across a DST change | Bucket alignment done in UTC instead of site-local | Buckets are aligned in `sites.timezone` then stored UTC (spec 5.2.5). Confirm the site timezone is a valid IANA name. |
| `IntegrityError` on a second primary zone version | Two open primary versions for one space | Close the old one (`effective_to = now`) before inserting the new (spec 5.2.2, 6.6). |

## M3: report

The Section 11 one-pager, HTML and PDF, generated from seeded data. No
deployment. `uv run whaletale-report --seed --out report`.

| Symptom | Cause | Action |
|---|---|---|
| `cannot load library 'libpango...'` on PDF render | WeasyPrint system libs missing | `sudo apt-get install libpango-1.0-0 libpangoft2-1.0-0` (in CI this is a workflow step). HTML output still works without them: use `--html-only`. |
| `error: no observations; run the seed first` | Empty database | `uv run whaletale-report --seed ...`, or seed separately. |
| Report "flagged as anomalous" for a whole week | The period contains a festival/closure day | Expected. The per-day anomaly table below the headline shows which day and its annotation. |
| Anomaly table slow on a long period | One `normalize_space` per day, each with its own trailing-weeks queries | Fine for a week or a month. A quarter-long report needs the day loop batched; not done yet. |

## M4: edge agent

`whaletale-agent` (multi-camera capture -> SQLite rollups) and `whaletale-sync`
(ship rollups + heartbeat) run as systemd services (`edge/deploy/`). Still no
central alerting - that is M8.

| Symptom | Cause | Action |
|---|---|---|
| `journalctl -u whaletale-agent` shows `camera <name>: cannot open source ...` | one camera unreachable; the others keep running | Check the camera's power and the RTSP URL in `/etc/whaletale/site.json`. The agent does not exit for one bad camera. |
| `whaletale-sync` logs `push failed: <urlerror> (will retry)` repeatedly | WAN down or cloud unreachable | Nothing to do on the box - rollups buffer in SQLite and ship when the link returns. Check `--dry-run` to see the backlog. |
| SQLite buffer growing without bound | sync has been failing for a long time | Fix connectivity. `prune_synced` only drops *shipped* rows; unsynced data is never discarded (spec 8.4). If the disk is critical, the operator-facing fix is more disk, not data loss. |
| `error: <path>: file is not a database` on agent start | corrupt SQLite file (power loss before WAL checkpoint, bad disk) | Move the file aside; the agent recreates it. Buffered-but-unsynced buckets in the corrupt file are lost - the gap is unrecoverable, same as a WAN outage past retention. |
| Buckets look an hour off around a DST change | edge authors `bucket_start` in UTC; nothing re-stamps it | Correct by design (spec 8.4). If it is genuinely wrong, check the box's NTP sync. |
| `active_cameras` lower than the camera count for some buckets | a camera dropped frames for part of that 15-minute window | Expected; the bucket is not extrapolated (spec 8.1). Persistent low counts mean a flaky camera. |

## M5: cloud API + sync

`whaletale-api` (FastAPI) exposes `POST /v1/ingest` and `POST /v1/heartbeat` for
the edge boxes. Auth is a per-box pairing token (`Authorization: Bearer`), stored
only as a SHA-256. Still no central alerting on the telemetry - that is M8.

| Symptom | Cause | Action |
|---|---|---|
| Edge `whaletale-sync` logs `HTTP 401` | token unknown or revoked | Re-pair the box: create a new `edge_boxes` row (M7 does this in the console; for now `pair_edge_box()` in a shell), put the new token in `/etc/whaletale/site.json`. |
| Edge logs `HTTP 403` | the payload's `site_id` does not match the token's site | The box config points at the wrong site. Fix `site_id` in `site.json`. |
| Edge logs `HTTP 422` on ingest | an observation references a `zone_version_id` not at this site | Stale zone config on the box, or the zone was reshaped. Re-fetch the zone config (M7); the buckets stay buffered and retry. |
| Edge logs `HTTP 409` | the box's payload schema is newer than the API | Deploy the newer cloud. The box keeps buffering. |
| `HTTP 429` from ingest | one box is pushing faster than the per-token limit (120/min) | Normal backpressure; the client retries. A persistent 429 means a misbehaving box - check its loop interval. |
| Ingest returns 200 but rows do not appear | the request hit a different API instance / DB | Confirm `DATABASE_URL`. Ingest is idempotent, so a resend is safe. |

## M6: operator console (backend)

The operator-facing REST API (`/v1/sites`, `/v1/spaces/{id}`, `/v1/sites/{id}/schedule`,
`/v1/sites/{id}/overview`, tenancy and zone-reshape writes). Auth is a hashed
bearer token per `operator_user`, scoped to that user's sites.

The Next.js console (`web/`) is being built screen by screen: Overview,
Schedule, Space detail, Spaces list, and Occupants ship first; the zone editor,
Reports, and Settings screens follow. Sign-in is email + operator token
(`create_operator_user` on the cloud) until a password flow lands.

| Symptom | Cause | Action |
|---|---|---|
| Console shows "not linked to a site" | the signed-in `operator_user` has no `operator_user_sites` row | Link it (Settings screen will do this; for now insert directly). |
| Schedule cell assignment fails with "already has an overlapping tenancy" | conflict detected on save | The message is from the API; the operator removes or edits the other tenancy first (spec 8.3). |
| Report PDF link 502s | the cloud report render failed or WeasyPrint libs missing on the API host | Check the API's `journalctl`; `libpango-1.0-0 libpangoft2-1.0-0` must be present. |
| Fonts fall back to a serif/sans on first load | `next/font` self-hosts IBM Plex at build; a stale build serves none | Rebuild the web app. |

| Symptom | Cause | Action |
|---|---|---|
| Console request returns 403 | the user is not linked to that site | Add an `operator_user_sites` row (the settings screen will do this in M8/M9). |
| `POST .../tenancies` returns 409 | overlaps an existing tenancy | The response body lists `conflicting_tenancy_ids`. The operator edits or removes the other tenancy first (spec 8.3). |
| Reshape returns 409 "no open primary" | the space has no primary zone version yet | The space was never onboarded (M7). Onboard the camera/zone first. |
| Schedule grid slow for a wide range | it resolves every (space, day) with RRULE expansion | Capped at 62 days per request. The console pages by month. |
| A renamed occupant still shows the old name somewhere | a cached response | The DB is correct (rename is in place, spec 8.3); the console just needs to refetch. |

## Later milestones

Filled in as each merges. Cloud/site alerting starts at M8.
