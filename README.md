# WhaleTale

Turns a property's existing security cameras into per-space foot-traffic data, so
the operator of a multi-tenant space (market, food hall, antique mall, mixed-use
retail) can price it, fill it, and prove its value.

Video never leaves the property. The edge box decodes RTSP, runs person
detection, applies zone logic, and writes counts to local SQLite. Only kilobyte
aggregates sync to the cloud. No frames, crops, embeddings, or track paths are
ever stored.

## Repository layout

| Path | Contents |
|---|---|
| `edge/` | On-prem agent: capture, detect, track, zone logic, aggregate, sync |
| `cloud/` | FastAPI API, Celery/arq workers, Alembic migrations |
| `web/` | Next.js operator console |
| `shared/` | Pydantic schemas, single source of truth for types |
| `docs/` | `licenses.md`, `metrics.md`, `runbook.md` |
| `docker/` | Compose files for edge and cloud |

## Status

M1: pipeline proof. Single stream, person detection, one hand-coded polygon,
entry counting to console. No database, no UI. See `CHANGELOG.md` for the
milestone list.

## Running the edge pipeline (M1)

Requires [`uv`](https://docs.astral.sh/uv/). The project pins Python 3.12; `uv`
downloads it if needed.

```bash
cd edge
uv sync
# Detect people in a zone from a video file, RTSP URL, or webcam:
uv run whaletale-edge --source /path/to/clip.mp4 --fps 4
uv run whaletale-edge --source rtsp://user:pass@camera/stream --fps 4
uv run whaletale-edge --source 0            # /dev/video0
```

The zone polygon is hard-coded in `edge/agent/zones.py` as normalized `[x, y]`
points in `0..1`. The run is split into fixed stream-time buckets
(`EDGE_BUCKET_SECONDS`, default 900) and prints per-bucket and run-total
entries, passersby, capture rate, occupied seconds, person-seconds, and dwell
p50/p90, plus the achievable decode+inference FPS.

Model weights download on first run to `EDGE_HF_CACHE` (default `edge/.hf_cache`)
and are git-ignored.

## Running the edge agent (M4)

The multi-camera daemon reads a per-box `site.json` (cameras, RTSP sources, zone
polygons with their cloud `zone_version_id`; never committed - see
`edge/site.example.json`), batches inference across streams, and writes
15-minute rollups to a local SQLite buffer.

```bash
cd edge
cp site.example.json site.json          # then edit for the real site
uv run whaletale-agent --config site.json --seconds 120
uv run whaletale-sync  --config site.json --dry-run    # show the buffered backlog
uv run whaletale-sync  --config site.json --once       # ship it (needs a cloud from M5)
```

`edge/deploy/` has the systemd units for a real box.

Onboard a camera (M7):

```bash
uv run whaletale-onboard --discover                       # WS-Discovery probe
uv run whaletale-onboard --source rtsp://u:p@cam/stream1 --name front-hall --emit
```

The gate checks the stream opens, resolution, decode FPS, and a timed test
inference; `--emit` prints a `site.json` block with the credentials sealed
(key from `WHALETALE_SITE_SECRET`).

## Cloud (M2: schema and attribution)

Postgres schema, synthetic seed, and the attribution / metrics / normalization
logic. No API or UI yet (M5, M6).

```bash
docker compose -f docker/compose.cloud.yml up -d   # Postgres + Redis
cd cloud
uv sync
uv run alembic upgrade head
WHALETALE_TEST_DATABASE_URL=postgresql+psycopg://whaletale:whaletale@localhost:5432/whaletale \
  uv run pytest
```

Without `WHALETALE_TEST_DATABASE_URL` the tests start a throwaway Postgres
container (needs Docker). Every schema change is an Alembic migration; CI fails
if the models and the migration head disagree.

Shared types live in `shared/schemas/` (Pydantic v2): the persisted-row models
and, from M5, the edge/cloud sync wire contract (`wire.py`). The cloud ORM
mirrors the row models and a test fails on drift. TypeScript generation arrives
with the web app in M6.

### Ingest API (M5)

```bash
cd cloud
DATABASE_URL=postgresql+psycopg://whaletale:whaletale@localhost:5432/whaletale \
  uv run whaletale-api --port 8000
```

`POST /v1/ingest` and `POST /v1/heartbeat` take a per-box pairing token
(`Authorization: Bearer ...`). Pair a box with `pair_edge_box()` (the operator
console does this in M7). The edge's `whaletale-sync` targets this API.

The same app serves the operator console API (M6 backend): `/v1/sites`,
`/v1/spaces/{id}`, `/v1/sites/{id}/schedule`, `/v1/sites/{id}/overview`, plus
tenancy and zone-reshape writes. Auth is a hashed bearer token per
`operator_user` (`create_operator_user()`), scoped to that user's sites.

The M3 report (Section 11 one-pager) is generated from seeded data:

```bash
uv run whaletale-report --seed --out report   # writes report.html and report.pdf
```

PDF rendering (WeasyPrint) needs `libpango-1.0-0 libpangoft2-1.0-0`; `--html-only`
skips it.

## Web (M6: operator console)

Next.js App Router + TypeScript. The visual world is a working drawing set —
flat ink on paper, hairline rules, the grid as the structure (see `DESIGN.md`).

```bash
cd web
pnpm install
cp .env.example .env.local          # set AUTH_SECRET and WHALETALE_API_URL
pnpm dev                            # needs the cloud API running (whaletale-api)
```

Sign in with an operator email and token (`create_operator_user` on the cloud).
Shipped screens: Overview, Schedule, Space detail, Spaces, Occupants. Zone
editor, Reports, and Settings are in progress.

## Development

```bash
uv tool install pre-commit
pre-commit install          # ruff, black, gitleaks on every commit
```

CI runs lint, type-check, tests, a secret scan, and a dependency license audit
that fails on any AGPL/GPL dependency (see `docs/licenses.md` for why).
