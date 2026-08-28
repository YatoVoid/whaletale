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

## M7: onboarding

`whaletale-onboard` on the edge box discovers cameras (WS-Discovery) or
validates a manual RTSP URL against the gate (opens < 10s, ≥ 640×480, decode
≥ 2 fps, test inference < 200ms, ≥ 1 clean frame). It seals the RTSP
credentials with a key derived from `WHALETALE_SITE_SECRET` and emits a
`site.json` camera block. The console pairs boxes and records validated
cameras.

| Symptom | Cause | Action |
|---|---|---|
| `whaletale-onboard --discover` finds nothing | cameras on a separate VLAN, or multicast blocked | Use `--source rtsp://…` with the URL from the camera's own admin page. |
| Validation `FAIL opens` | wrong RTSP path or credentials, camera unreachable | Confirm the URL plays in `ffplay`. |
| Validation `FAIL achievable fps` on a real camera | the box is CPU-only or overloaded | Expected on a Jetson / no-GPU box; M4 batching and a GPU fix it. The gate is advisory here — re-run with the target hardware. |
| `FAIL test inference` | model not cached, or the box is too slow | Pre-warm with `whaletale-agent --warm`; on a slow box, `--no-inference` skips this one check. |
| Console "Add camera" 422 | resolution not `WxH` | Enter e.g. `1920x1080`. |
| Sealed credentials won't decrypt on the box | `WHALETALE_SITE_SECRET` differs from when they were sealed | Re-run `whaletale-onboard --emit` with the current secret. |

## M8: fleet admin + alerts

`GET /admin/fleet` (staff token `WHALETALE_ADMIN_TOKEN`) shows every site's
health state and open alert conditions; `POST /admin/fleet/evaluate` persists
them into `alerts` (run it on a schedule in prod). Sentry is wired but inert
unless `SENTRY_DSN` is set.

Alert conditions (spec 9): a camera dark > 1h → **customer**, plain language
("Camera 4 has been offline since … Check that it has power"); sync stale > 6h,
disk < 20%, mean confidence down > 30% from baseline, agent version behind → **us**.

| Symptom | Cause | Action |
|---|---|---|
| `/admin/fleet` → 401 | `WHALETALE_ADMIN_TOKEN` unset or the bearer doesn't match | Set the env var on the API host; it's staff-only. |
| A `disk_low` alert never fires on a real box | old agent that doesn't send `disk_total_bytes` | Upgrade the agent (M8 edge change). Free-bytes alone can't give a ratio. |
| `per_camera` confidence stays empty in the fleet view | `whaletale-agent` and `whaletale-sync` are pointed at different `EDGE_SQLITE_PATH` values | They must share the file: the agent writes `camera_health`, the sync process reads it into the heartbeat. |
| Alerts don't clear after the box recovers | `POST /admin/fleet/evaluate` hasn't run since | Schedule it (every few minutes). It resolves rows whose condition is gone. |
| `low_confidence` noisy at dawn/dusk | IR switch / low sun; the baseline hasn't caught up | Expected transient. Persistent means a moved or failing camera (spec 8.1). |

## M9: billing

Stripe subscription per site, quantity = the number of `cameras` rows
(recomputed server-side, never trusted from the client). `GET .../billing`,
`GET .../billing/preview`, `POST .../billing/apply`. Stripe events hit
`POST /webhooks/stripe`, signature-verified.

| Symptom | Cause | Action |
|---|---|---|
| Console shows "read-only" | payment failed and the grace window (`WHALETALE_BILLING_GRACE_DAYS`) has elapsed | The customer resolves payment in Stripe; `invoice.paid` clears it. Ingest and heartbeats keep running the whole time (spec 8.5). |
| `.../billing/preview` → 409 "no subscription" | the site was never set up in Stripe | Create the customer + subscription and insert a `subscriptions` row. |
| Adding a camera didn't change the bill | `apply` wasn't called after `register_camera`, or the count matched | The preview → confirm flow in Settings calls `apply`. Removes only take effect next period (spec 8.5). |
| Webhook returns 400 | bad `Stripe-Signature` or `STRIPE_WEBHOOK_SECRET` unset | Check the signing secret matches the endpoint's in the Stripe dashboard. |
| A canceled site still shows data | export window (`WHALETALE_BILLING_EXPORT_DAYS`) | Data is retained until `export_ready_at` passes, then a separate job deletes it. |

## M10: hardening

`docs/edge-cases.md` is the full spec §8 coverage matrix (done / partial /
deferred, with the test that pins each). New this milestone:

- **Re-entry grace window (spec 8.2).** An occluded person reappears under a
  fresh track id. The counter parks a dropped track for `EDGE_REENTRY_SECONDS`
  and lets a new track starting within `EDGE_REENTRY_DISTANCE` inherit its
  visit instead of counting a second entry. `ZoneStats.reentries_merged` counts
  how often this fired. Set either env var to 0 to disable.
- **Optimistic locking on zone reshape (spec 8.4).** The editor loads
  `GET /v1/spaces/{id}/zone-versions/current` and sends its `zone_version_id`
  back as `base_version_id`. If another operator reshaped in between, the save
  is refused with 409 "this zone changed since you opened it".
- **API security headers.** Every response carries HSTS, `X-Content-Type-Options`,
  `X-Frame-Options: DENY`, `Referrer-Policy`, and a locked-down CSP.
- **Auth lockout + security-event log.** After 10 failed auth attempts from one
  IP in 15 minutes, the ingest / operator / admin auth paths return 429 until
  the window passes; a successful auth clears the counter. Every auth failure,
  permission denial, rate-limit hit, and admin action is one line on the
  `whaletale.security` logger. State is in-process; a scaled deployment moves
  both the throttle and the rate limiter to Redis.

| Symptom | Cause | Action |
|---|---|---|
| Entry counts look low after tuning | `EDGE_REENTRY_DISTANCE` too large in a busy crossing scene, so distinct people get merged | Lower it; check `reentries_merged` against expected occlusion frequency. |
| Zone save fails with 409 "changed since you opened it" | another operator reshaped the same zone | Reload the editor (it refetches the current version) and reapply. |
| Zone save shows "overlaps another zone on the same camera" | the polygon overlaps another space's zone by IoU >= 0.02 | Intended when a table sits inside a patio: set the parent/child relation on the space, or use "Save with the overlap". |
| A partial/deferred §8 item bites in the pilot | see `docs/edge-cases.md` "Deferred, tracked" | Each has a concrete build note; none block the pilot. |
| An edge box or operator gets 429 on a valid token | 10 failed auth attempts from that IP in the last 15 min tripped the lockout | Wait out the window, or restart the API process to clear in-process state. Check `whaletale.security` for the failing attempts. |

## Later milestones

Cloud/site alerting starts at M8. M10 is the final spec milestone.
