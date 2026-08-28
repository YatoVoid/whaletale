# Section 8 edge-case coverage

Spec §8 lists every failure mode the system has to survive. This is the
milestone-10 audit: for each item, where it is handled and the test that pins
it, or an honest note on what is still missing and why.

Status key: **done** (handled and tested), **partial** (the core is handled,
a named refinement is not), **deferred** (not built, tracked below).

## 8.1 Camera and stream

| Case | Status | Where / test |
|---|---|---|
| Camera offline mid-bucket, mark partial, record `active_cameras`, no extrapolation | done | `pipeline.py` writes `active_cameras` per site-total from the set of cameras that produced a bucket; `test_wire_contract.test_edge_site_total_row_parses`, `test_admin_api.test_fleet_reports_state_and_alerts` |
| Camera clock drift, reject frames > 60s from local time | not applicable | The agent stamps each frame with the box wall clock (`_CameraWorker`), never the camera's own timestamp, so a drifted camera clock cannot reach a bucket. Box-clock NTP is a deploy concern (`docs/runbook.md`). There is nothing to reject. |
| Camera moved / re-aimed, perceptual hash vs hourly reference, flag `needs_recalibration`, stop counting | done | `calibration.py` (dHash + `DriftDetector` + on-box `RefStore`); the pipeline auto-captures a reference on the first check, re-checks hourly, and on sustained divergence flags the camera, stops feeding it to counting, and reports `needs_recalibration` in the heartbeat. The cloud raises a customer `camera_moved` alert. `whaletale-agent --recalibrate` re-captures references after a deliberate move. `test_calibration.*`, `test_pipeline.test_camera_drift_flags_and_pauses_counting`, `test_fleet.test_camera_moved_alerts_the_customer` |
| Resolution / aspect ratio change, normalized polygons survive, flag for review | partial | Polygons are normalized end to end (`zones.py`, `test_zones.test_parse_zone_variants`); the review flag is not emitted. |
| Frozen frame (identical consecutive frames > 30s), treat as offline | done | `decode.FrozenFrameDetector`, wired into `_CameraWorker`; a stalled source sets a `frozen frame` worker error like a decode failure. `EDGE_FROZEN_FRAME_SECONDS` (default 30). `test_decode.test_frozen_frame_detector_*`, `test_pipeline.test_frozen_stream_surfaces_a_worker_error` |
| RTSP credentials rotated, specific operator-facing message | partial | `DecodeError` surfaces the underlying error string (`test_decode.test_file_decode_failure_is_fatal`); it is not classified as an auth failure with dedicated copy. |
| Night mode / IR switch, per-camera confidence baseline, flag `low_confidence` | partial | End to end: the agent tracks a rolling per-camera mean detection confidence and fps, writes them to the local `camera_health` table (`pipeline._flush_camera_health`, `test_pipeline`), the sync client puts them in the heartbeat `per_camera` block, and the cloud derives the drop (`fleet._confidence_baseline`, `FleetConfig.confidence_drop`, `test_fleet.test_confidence_drop_from_baseline`). Not yet done: stamping `low_confidence` on individual observation rows. |
| Direct sun / blown highlights, same mechanism | partial | Same as above. |

## 8.2 Detection and tracking

| Case | Status | Where / test |
|---|---|---|
| Occluded person reappears under a new track id, inflates entries, re-entry grace window (N seconds, M pixels) | done | `counter.py` `_claim_parked` / `_expire_parked`, config `reentry_seconds` / `reentry_distance` (env `EDGE_REENTRY_SECONDS` / `EDGE_REENTRY_DISTANCE`); `test_counter.test_occluded_reappearance_is_one_entry`, `test_new_track_outside_the_window_is_a_fresh_entry`, `test_new_track_far_away_is_a_fresh_entry` |
| Loitering at a boundary, `min_dwell_seconds` plus hysteresis | done | `zones.py` separate enter / stay thresholds; `test_counter.test_loitering_on_boundary_does_not_double_count` |
| Staff walking through repeatedly, excluded zones plus a "staff hours" report filter | partial | Excluded zones are done on the edge: a zone with `"excluded": true` in the site config becomes an `ExclusionMask`, and any detection whose ground point falls inside is dropped before any counting zone sees it (`pipeline._drop_excluded`). `test_siteconfig.test_excluded_zone_*`, `test_pipeline.test_excluded_zone_masks_staff_detections`. Still deferred: creating an excluded zone through the console (needs an `EXCLUDED` space kind), and the report-time staff-hours window filter. |
| Glass-storefront reflections counted as people, operator marks polygon sub-regions excluded | deferred | Sub-region exclusion is unbuilt. |
| Groups moving together, detection handles it, note a family of four counts as four | done (doc) | Model behavior; stated in this file's Known limitations. |
| Children, wheelchairs, strollers, verify the model detects these or note the limitation | done (doc) | Stated in Known limitations. |
| Empty site overnight, do not zero-fill outside operating hours, store operating hours per site | partial | The edge emits a bucket only when a zone produced activity, so it does not zero-fill; there is no explicit per-site `operating_hours` suppression. |

## 8.3 Zones and tenancy

| Case | Status | Where / test |
|---|---|---|
| Zone with < 3 points, reject at the UI | done | `validation.assert_saveable_polygon`, web zone editor guard; `test_validation.test_polygon_needs_three_points`, `test_zones.test_zone_rejects_fewer_than_three_points` |
| Self-intersecting polygon, refuse to save | done | `test_validation.test_self_intersecting_polygon_is_rejected`, `test_zones.test_zone_rejects_self_intersecting_polygon`, `test_operator_api.test_reshape_rejects_a_self_intersecting_polygon` |
| Zone entirely outside frame bounds, reject | done | `test_validation.test_polygon_must_be_inside_the_frame`, `test_siteconfig.test_invalid_configs_are_rejected` |
| Two zones overlapping on one camera, allowed but warn and confirm parent/child | done | `validation.find_zone_overlaps` (IoU against every other open primary on the camera); `reshape_zone` returns a 409 `zone_overlap` with the overlapping spaces unless they are already in a parent/child relation with the edited space or `acknowledge_overlap` is set. The console zone editor shows the warning and a "Save with the overlap" button. `test_validation.test_zone_overlap_*`, `test_operator_api.test_reshape_warns_on_zone_overlap_then_saves_when_acknowledged` |
| Space with no tenancy for a period, report as vacant | done | `attribution.py`; `test_attribution.test_never_leased_space_is_all_vacant`, `test_tenancy_gap_reads_as_vacant_between_two_occupants` |
| Overlapping tenancies on one space, reject on save, show the conflict | done | `validation.find_tenancy_conflicts`; `test_validation.test_overlapping_permanent_tenancy_is_a_conflict`, `test_same_weekday_overlapping_daily_windows_conflict`, `test_operator_api.test_create_tenancy_then_conflict` |
| Tenancy edited retroactively, recompute affected periods | done | Attribution joins at query time; `test_attribution.test_retroactive_tenancy_edit_recomputes` |
| Recurring tenancy on a day the venue was closed, cross-reference `day_annotations`, suppress | done | `test_attribution.test_closure_annotation_suppresses_an_otherwise_occupied_bucket` |
| Occupant renamed or merged, records referenced not copied | done | `test_attribution.test_occupant_rename_propagates_to_history`, `test_operator_api.test_create_and_rename_occupant` |
| Timezone / DST boundary on a recurring Saturday, RRULE with an explicit timezone | done | `normalization.py` / `schedule.py` shift wall-clock in the site tz; `test_attribution.test_recurring_tenancy_is_saturday_only_and_within_daily_window`, `test_normalization.test_festival_saturday_is_flagged_as_an_anomaly` |

## 8.4 System and data

| Case | Status | Where / test |
|---|---|---|
| Edge box offline for days, SQLite buffers, sync idempotent and resumable with a watermark | done | `store.py` `synced_at IS NULL` watermark, `sync/client.py`; `test_sync_client.test_offline_leaves_rows_for_retry`, `test_non_2xx_is_not_acked`, `test_drain_pushes_everything_in_batches` |
| Duplicate sync payload, upsert on `(zone_version_id, bucket_start)` | done | `test_api.test_ingest_upserts_and_is_idempotent`, `test_store.test_upsert_overwrites_and_rearms_for_sync` |
| Edge disk fills, rotate oldest synced buckets, alert at 80% | done | `store.prune_synced`, fleet `disk_low_fraction` 0.20; `test_store.test_prune_keeps_unsynced_and_recent_synced`, `test_fleet.test_disk_low` |
| Power loss mid-write, SQLite WAL, verify integrity on boot | done | `store.py` WAL + `PRAGMA integrity_check`; `test_store.test_integrity_check_rejects_a_non_database_file` |
| Edge box replaced, site re-pairs with a token, historical cloud data intact | done | `pairing.py`, operator onboarding pair / revoke; `test_operator_onboarding.test_pair_edge_box_returns_a_token_once`, `test_revoke_box_drops_it_from_the_list` |
| Schema version mismatch, cloud accepts older payloads and upgrades them | partial | Cloud rejects a newer `schema_version` (`test_api.test_newer_schema_version_is_409`). Only v1 exists, so "accept older" has nothing to exercise yet; the version gate is in place for when it does. |
| Clock skew edge vs cloud, timestamps authored on the edge in UTC, cloud never re-stamps | done | `test_api.test_bucket_timestamp_is_stored_verbatim_never_restamped` |
| Two operators editing zones at once, optimistic locking on `zone_versions`, conflict warning | done | `ReshapeIn.base_version_id` checked against the open primary in `routes.reshape_zone`, `GET .../zone-versions/current` to load it; `test_operator_api.test_reshape_conflicts_when_base_version_is_stale` |

## 8.5 Commercial

| Case | Status | Where / test |
|---|---|---|
| Camera added mid-period, show prorated change before confirming, never charge silently | done | `billing.preview_change` then `apply_change`; `test_billing.test_preview_reflects_the_live_camera_count`, `test_apply_add_prorates_immediately` |
| Camera removed, prorate down next period, no mid-period refund | done | `apply_change` uses `proration_behavior="none"` on decreases; `test_billing.test_apply_remove_defers_to_next_period` |
| Payment fails, grace period, dashboard read-only, edge keeps collecting | done | `is_read_only` after `grace_until`, `_require_writable` 402 on operator writes, ingest and heartbeat never gated; `test_billing.test_past_due_is_writable_during_grace_then_read_only`, `test_operator_write_is_402_when_read_only`, `test_ingest_is_never_gated_by_billing` |
| Customer cancels, data export offered then deletion after a stated window | done | `handle_webhook` on `customer.subscription.deleted` sets `export_ready_at`; `test_billing.test_subscription_deleted_starts_export_window` |

## Deferred, tracked

These need a schema or product decision beyond a hardening pass, or edge-only
work with a captured-frame constraint. None block the pilot; each is a known
gap.

1. **`low_confidence` on observation rows (§8.1).** The per-camera confidence
   signal now reaches the cloud fleet view; the remaining piece is stamping a
   `low_confidence` flag on the individual `observations` rows a camera
   produced while its confidence was depressed, so a report can grey them out.
2. **Excluded zones in the console + staff-hours filter (§8.2).** The edge
   masking is done. Remaining: an `EXCLUDED` space kind so an operator can draw
   an excluded zone in the console (today it is authored in the site config),
   and a report-time toggle that drops configured staff-hour windows.
3. **Glass-reflection sub-region exclusion (§8.2).** Let the operator mark
   holes inside a zone polygon that do not count.
4. **Operating hours per site (§8.2).** Store open/close per weekday and skip
   bucket emission outside them rather than relying on "no activity, no bucket".

Customer-audience fleet alerts (`camera_dark`, `camera_moved`) currently
surface only through `/admin/fleet` and `/admin/alerts`. An operator-facing
alerts endpoint and a console banner are a separate piece of work.

## Known limitations

- Detection counts individuals. A group of four people reads as four entries;
  there is no group or household de-duplication and there should not be.
- Recall on children, wheelchair users, and people pushing strollers depends on
  the person-detection model. It is not separately validated. Treat per-camera
  counts for spaces with heavy stroller or wheelchair traffic as a floor.
- The system never identifies individuals. Staff exclusion is geometric
  (excluded zones), not biometric.
