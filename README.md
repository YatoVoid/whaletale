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

M1 — pipeline proof. Single stream, person detection, one hand-coded polygon,
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

The zone polygon for M1 is hard-coded in `edge/agent/zones.py` as normalized
`[x, y]` points in `0..1`. The run prints per-zone entries, occupied seconds,
and dwell p50/p90, plus the achievable decode+inference FPS.

Model weights download on first run to `EDGE_HF_CACHE` (default `edge/.hf_cache`)
and are git-ignored.

## Cloud / web

Not built yet. Arrive in M5 and M6.

## Development

```bash
uv tool install pre-commit
pre-commit install          # ruff, black, gitleaks on every commit
```

CI runs lint, type-check, tests, a secret scan, and a dependency license audit
that fails on any AGPL/GPL dependency (see `docs/licenses.md` for why).
