# Dependency license audit

This is a commercial closed-source product. AGPL-3.0 would require releasing our
source to anyone using the product over a network. **No AGPL, GPL, or
"research only" dependency goes in.** CI fails the build on any AGPL/GPL match
(`scripts/license_audit.py`).

Before adding any vision dependency, check its license and add a row here.

## Banned (do not add, ever)

| Package | Reason |
|---|---|
| `ultralytics` (YOLOv5/v8/v11) | AGPL-3.0 |
| Any checkpoint whose license inherits from Ultralytics | AGPL-3.0 |
| DeepSORT implementations that vendor AGPL code | AGPL-3.0 |

## Approved and in use

| Purpose | Package | License | Checked |
|---|---|---|---|
| Object detection (M1) | `transformers` (RT-DETR, `PekingU/rtdetr_r50vd` / `r18vd`) | Apache-2.0 | 2026-08-27 |
| Inference runtime (M1) | `torch` | BSD-3-Clause | 2026-08-27 |
| Image transforms (M1) | `torchvision` | BSD-3-Clause | 2026-08-27 |
| Video decode | `av` (PyAV, links FFmpeg) | BSD-3-Clause (FFmpeg LGPL, dynamic link) | 2026-08-27 |
| Tracking | `norfair` | MIT | 2026-08-27 |
| Polygon geometry | `shapely` | BSD-3-Clause | 2026-08-27 |
| Credential encryption (M7) | `cryptography` (+ `cffi`, `pycparser`) | Apache-2.0 / BSD-3-Clause | 2026-08-28 |
| WS-Discovery camera probe (M7) | `wsdiscovery` (+ `ifaddr`) | LGPLv3+ / MIT | 2026-08-28 |
| ONVIF device query (M7, optional extra) | `onvif-zeep` | MIT | 2026-08-28 |
| Numerics | `numpy` | BSD-3-Clause | 2026-08-27 |
| Imaging | `pillow` | MIT-CMU | 2026-08-27 |

## Approved and in use — cloud (M2)

| Purpose | Package | License | Checked |
|---|---|---|---|
| ORM | `sqlalchemy` | MIT | 2026-08-27 |
| Migrations | `alembic` (+ `mako`) | MIT | 2026-08-27 |
| Postgres driver | `psycopg` / `psycopg-binary` | LGPL-3.0-only | 2026-08-27 |
| Schemas | `pydantic`, `pydantic-settings` | MIT | 2026-08-27 |
| Recurrence (RRULE) | `python-dateutil` | BSD-3-Clause / Apache-2.0 (dual) | 2026-08-27 |
| Polygon geometry | `shapely` | BSD-3-Clause | 2026-08-27 |
| Test Postgres (dev) | `testcontainers` | Apache-2.0 | 2026-08-27 |
| Report templating (M3) | `jinja2` | BSD-3-Clause | 2026-08-28 |
| HTML to PDF (M3) | `weasyprint` (+ `pydyf`, `tinycss2`, `tinyhtml5`) | BSD-3-Clause | 2026-08-28 |
| Hyphenation, via WeasyPrint | `pyphen` | GPLv2+ / LGPLv2+ / MPL-1.1 (disjunctive) | 2026-08-28 |
| Ingest API (M5) | `fastapi` | MIT | 2026-08-28 |
| ASGI toolkit / server (M5) | `starlette`, `uvicorn` (+ `uvloop`, `httptools`, `websockets`, `watchfiles`) | BSD-3-Clause / MIT | 2026-08-28 |
| HTTP client, test transport (M5) | `httpx` (+ `anyio`, `h11`) | BSD-3-Clause / MIT | 2026-08-28 |
| Error tracking (M8) | `sentry-sdk` | MIT | 2026-08-28 |
| Billing (M9) | `stripe` | MIT | 2026-08-28 |

`psycopg` is LGPL-3.0. Same standing as FFmpeg (Section 3): the library is
imported unmodified and runs server-side, never distributed to a user, so the
LGPL relink obligation is not triggered. The license audit allows LGPL; it fails
only on AGPL/GPL.

`pyphen` is disjunctively licensed (GPLv2+ **or** LGPLv2+ **or** MPL-1.1); we
take the LGPL/MPL arm. `license_audit.py` clears a GPL classifier when an LGPL
or permissive classifier sits beside it on the same distribution.

## Transitive, reviewed

| Package | Via | License | Note |
|---|---|---|---|
| `filterpy` | `norfair` | MIT | Kalman filtering |
| `matplotlib` | `norfair` → `filterpy` | PSF-style (non-copyleft) | Allowlisted in `license_audit.py`: its bundled LICENSE text quotes GPL notices for third-party parts and trips keyword scans. Unwanted weight on an edge box; revisit trimming `filterpy`'s deps in M4. |

## Model checkpoints

| Checkpoint | License | Notes |
|---|---|---|
| `PekingU/rtdetr_r50vd` | Apache-2.0 | RT-DETR trained on COCO; person = class 0 |

## Planned, not yet added

- `supervision` (MIT): polygon annotation / line-crossing overlay. Not needed
  for M1 (geometry is `shapely`); lands with the M6 zone editor overlay.
- FastAPI, `arq` / Celery + Redis, WeasyPrint or Playwright (M3/M5).
- RT-DETR/YOLOX ONNX export, ONNX Runtime or TensorRT (M4).
- `onvif-zeep` / `WSDiscovery` (M7).

Check and record each when added.
