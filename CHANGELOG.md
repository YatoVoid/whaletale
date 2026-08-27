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

<!--
Later milestones (planned):
M2 schema + attribution · M3 report · M4 edge agent · M5 cloud API + sync
M6 operator console · M7 onboarding · M8 fleet admin · M9 billing · M10 hardening
-->
