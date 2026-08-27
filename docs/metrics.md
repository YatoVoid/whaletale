# Metrics

These definitions are canonical. The operator console links every metric label to
this file. Do not redefine any of these anywhere else in the codebase or UI;
import the constants and helpers from `shared/` once they exist.

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

## M1 status

M1 implements: entry (with `min_dwell_seconds` and separate enter/exit
thresholds), occupied seconds, and dwell p50/p90 for a single hard-coded zone.
Passerby, capture rate, traffic share, and normalization arrive with the schema
in M2.
