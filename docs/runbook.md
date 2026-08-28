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

## Later milestones

Filled in as each merges. Cloud/site alerting starts at M8.
