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
| Numerics | `numpy` | BSD-3-Clause | 2026-08-27 |
| Imaging | `pillow` | MIT-CMU | 2026-08-27 |

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
- RT-DETR/YOLOX ONNX export, ONNX Runtime or TensorRT (M4).
- `onvif-zeep` / `WSDiscovery` (M7).

Check and record each when added.
