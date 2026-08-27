# Runbook

What to do when a site alerts. One section per milestone on how that milestone
fails and the response.

## M1: pipeline proof

Local dev only, no deployment, no alerts. Failure modes seen while running
`whaletale-edge`:

| Symptom | Cause | Action |
|---|---|---|
| `av.error.*` opening the source | Bad path, wrong RTSP creds, camera unreachable | Verify the source plays in `ffplay`. For RTSP, check credentials and that the box can route to the camera. |
| First run hangs for minutes | RT-DETR weights downloading to `EDGE_HF_CACHE` | Wait once; cached afterwards. Pre-warm with `uv run whaletale-edge --warm`. |
| Achievable FPS well below `--fps` on CPU | RT-DETR PyTorch on a CPU-only box measured ~0.2 fps (`r50vd`) / ~0.5 fps (`r18vd`) single stream | Expected for the proof. M4 exports to ONNX/TensorRT and batches across cameras; the reference edge box has an RTX 3060. Use `--model PekingU/rtdetr_r18vd` for faster iteration. |
| Entry count looks inflated | Track ID churn from occlusion; no re-entry grace window yet | Known M1 limitation. Re-entry merge (spec 8.2) lands in M4. |
| Zero entries but people are visible | Polygon doesn't cover where people walk | Adjust the normalized points in `edge/agent/zones.py`. Live overlay editor is M6. |

## Later milestones

Filled in as each merges. Cloud/site alerting starts at M8.
