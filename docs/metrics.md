# Metrics

These definitions are canonical. The operator console links every metric label to
this file. Do not redefine any of these anywhere else in the codebase or UI.
Shared types live in `shared/schemas/`; the cloud computes the metrics in
`cloud/whaletale_cloud/metrics.py` and normalization in `normalization.py`.

## Definitions (spec Section 6.4)

- **Entry.** A tracked person's ground point transitions outside → inside a zone
  polygon and remains inside for ≥ `min_dwell_seconds` (default 3s). The
  threshold suppresses boundary jitter.
- **Occupied seconds.** Wall-clock seconds during which ≥ 1 person was inside.
  Not a sum over people.
- **Person-seconds.** Sum over all people of time inside. A different metric
  from occupied seconds; label it differently and never confuse the two.
- **Dwell.** Per-track duration inside a zone, reported as median and p90. Never
  as a mean: one person who left a bag in frame ruins a mean.
- **Passerby.** A track whose ground point enters the zone's *catchment*
  (a configurable dilation of the polygon, default 2 m equivalent) but never
  enters the zone itself.
- **Capture rate.** `entries / (entries + passersby)`. The most valuable number
  in the product: it separates appeal from location. A stall on a dead corridor
  with 40% capture is a good tenant in a bad spot.
- **Traffic share.** `zone entries / site_totals.total_people` for the same
  bucket. The number that survives busy days and slow days.

## Ground point

The ground point of a detection is the **bottom-centre of the bounding box**,
never the box centre. A tall person at the frame edge would otherwise be
attributed to the wrong zone.

## Normalization (spec Section 6.5)

Every reported figure carries three comparisons: share of site, against itself
(same weekday, trailing four weeks, same hours), and against peer zones of the
same `kind`. Weekday-to-weekday comparison is never a default. Anomalies
(> 2 SD from the trailing baseline) are surfaced and annotated, never silently
excluded.

## Implementation status

The edge agent computes, per fixed stream-time bucket (`bucket_seconds`,
default 900) for a single hard-coded zone: entry (with `min_dwell_seconds` and
separate enter/exit thresholds), occupied seconds, person-seconds, dwell
p50/p90, passerby (catchment is the polygon dilated by `catchment_frac`, a
normalized-space stand-in for the "2 m equivalent" until ground-plane
calibration), and capture rate.

Bucketing rule (assumption, pending spec confirmation): time metrics (occupied,
person-seconds) split at the boundary; event metrics (entries, dwell samples,
passersby) are attributed to the bucket where the event resolves (an entry to
where `min_dwell` is met, a dwell to where the track leaves or the run ends, a
passerby to where the track is dropped). Track identity is continuous across
boundaries.

The cloud (M2) computes the same metrics over synced 15-minute `observations`,
joined to `tenancies` at query time so a schedule fixed weeks late corrects all
history (spec 5.2.1). Each bucket is resolved against the zone version effective
then (spec 5.2.2); a bucket the primary version is missing falls back to a
non-primary version and is marked `degraded` (spec 6.6). Normalization does all
three comparisons; the trailing-weeks shift is done in the site timezone so a
DST boundary does not misalign "10am Saturday" (spec 5.2.5).

Two metrics are not fully reconstructable in the cloud from the 5.1 schema and
are handled honestly rather than faked:

- **Person-seconds** has no `observations` column, so it is not reported at the
  cloud. The edge computes it but does not sync it.
- **Dwell** is stored per bucket as p50/p90. A true period percentile needs the
  per-track samples, which are not synced, so the period figure is the
  entries-weighted mean of the bucket percentiles, labelled `_est`.

`capture_events` is the stored numerator for capture rate; the edge sets it
equal to `entries`, so the reported rate matches the 6.4 formula.
