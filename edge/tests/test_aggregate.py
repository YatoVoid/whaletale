from __future__ import annotations

import pytest

from agent.aggregate import RunAggregator
from agent.counter import ZoneCounter
from agent.zones import Zone

INSIDE = (0.5, 0.5)
CATCHMENT = (0.5, 0.70)
OUTSIDE = (0.5, 0.95)


def make_zone() -> Zone:
    return Zone(
        "sq",
        [(0.4, 0.4), (0.6, 0.4), (0.6, 0.6), (0.4, 0.6)],
        exit_margin=0.05,
        catchment_margin=0.15,
    )


def test_rejects_non_positive_bucket_seconds() -> None:
    with pytest.raises(ValueError):
        RunAggregator(make_zone(), min_dwell_seconds=3.0, bucket_seconds=0)


def test_short_run_is_one_bucket_matching_a_plain_counter() -> None:
    agg = RunAggregator(make_zone(), min_dwell_seconds=0.0, bucket_seconds=10_000)
    ref = ZoneCounter(make_zone(), min_dwell_seconds=0.0)
    for t in (0.0, 1.0, 2.0, 3.0):
        agg.update(t, {1: INSIDE})
        ref.update(t, {1: INSIDE})
    buckets = agg.finalize(3.0)
    ref.finalize(3.0)

    assert len(buckets) == 1
    b = buckets[0].stats
    assert b.entries == ref.stats.entries == 1
    assert b.occupied_seconds == pytest.approx(ref.stats.occupied_seconds)
    assert b.person_seconds == pytest.approx(ref.stats.person_seconds)


def test_time_metrics_split_at_boundaries_events_land_where_they_resolve() -> None:
    agg = RunAggregator(make_zone(), min_dwell_seconds=0.0, bucket_seconds=10.0)
    for t in range(26):
        agg.update(float(t), {1: INSIDE})
    buckets = agg.finalize(25.0)

    assert [b.start for b in buckets] == [0.0, 10.0, 20.0]
    assert [b.stats.entries for b in buckets] == [1, 0, 0]  # entry resolves at t=1
    # Occupancy: [1..10] then [10..20] then [20..25]; the track is PENDING at t=0.
    assert [round(b.stats.occupied_seconds) for b in buckets] == [9, 10, 5]
    assert [round(b.stats.person_seconds) for b in buckets] == [9, 10, 5]
    # Dwell closes at finalize, in the bucket in progress then.
    assert buckets[2].stats.dwell_samples == [pytest.approx(25.0)]

    totals = agg.totals()
    assert totals.entries == 1
    assert totals.occupied_seconds == pytest.approx(24.0)
    assert totals.person_seconds == pytest.approx(24.0)
    assert totals.dwell_samples == [pytest.approx(25.0)]


def test_buckets_align_to_the_stream_time_grid() -> None:
    agg = RunAggregator(make_zone(), min_dwell_seconds=0.0, bucket_seconds=10.0)
    for t in (13.0, 14.0, 15.0):
        agg.update(t, {1: OUTSIDE})
    buckets = agg.finalize(15.0)
    assert buckets[0].start == 10.0


def test_passerby_lands_in_the_bucket_it_is_classified_in() -> None:
    agg = RunAggregator(make_zone(), min_dwell_seconds=3.0, bucket_seconds=10.0)
    for t in range(16):
        agg.update(float(t), {1: CATCHMENT})
    buckets = agg.finalize(15.0)

    assert [b.stats.passersby for b in buckets] == [0, 1]
    assert agg.totals().passersby == 1


def test_finalize_before_any_update_returns_no_buckets() -> None:
    agg = RunAggregator(make_zone(), min_dwell_seconds=3.0, bucket_seconds=10.0)
    assert agg.finalize(5.0) == []


def test_end_track_closes_dwell_in_the_current_bucket() -> None:
    agg = RunAggregator(make_zone(), min_dwell_seconds=0.0, bucket_seconds=100.0)
    for t in (0.0, 1.0, 2.0, 3.0):
        agg.update(float(t), {7: INSIDE})
    agg.end_track(7, 5.0)  # tracker dropped the id while still inside
    buckets = agg.finalize(5.0)
    assert buckets[0].stats.dwell_samples == [pytest.approx(5.0)]


def test_entries_so_far_includes_the_in_progress_bucket() -> None:
    agg = RunAggregator(make_zone(), min_dwell_seconds=0.0, bucket_seconds=10.0)
    agg.update(0.0, {1: INSIDE})
    agg.update(1.0, {1: INSIDE})  # entry resolves here, still in bucket 0
    assert agg.entries_so_far == 1
    assert agg.buckets == []  # bucket 0 not flushed yet


# --- WallClockAggregator ---------------------------------------------------

from datetime import UTC, datetime, timedelta  # noqa: E402

from agent.aggregate import WallClockAggregator, WallClockBucket  # noqa: E402


def _wc_zone() -> Zone:
    return Zone(
        "sq",
        [(0.4, 0.4), (0.6, 0.4), (0.6, 0.6), (0.4, 0.6)],
        exit_margin=0.05,
        catchment_margin=0.15,
    )


def test_wallclock_buckets_align_to_the_15_minute_grid() -> None:
    got: list[WallClockBucket] = []
    agg = WallClockAggregator(_wc_zone(), got.append, min_dwell_seconds=0.0, bucket_seconds=900)
    base = datetime(2026, 6, 1, 10, 7, tzinfo=UTC)  # 10:07 -> bucket 10:00
    for i in range(0, 20):
        agg.update(base + timedelta(minutes=i), {1: INSIDE})
    agg.close(base + timedelta(minutes=20))

    starts = [b.start for b in got]
    assert starts[0] == datetime(2026, 6, 1, 10, 0, tzinfo=UTC)
    assert starts[1] == datetime(2026, 6, 1, 10, 15, tzinfo=UTC)
    assert all(b.end - b.start == timedelta(minutes=15) for b in got[:-1])


def test_wallclock_entry_lands_in_the_bucket_it_resolves_in() -> None:
    got: list[WallClockBucket] = []
    agg = WallClockAggregator(_wc_zone(), got.append, min_dwell_seconds=0.0, bucket_seconds=600)
    base = datetime(2026, 6, 1, 10, 0, tzinfo=UTC)
    # inside for 25 minutes across two 10-minute boundaries
    for i in range(0, 26):
        agg.update(base + timedelta(minutes=i), {1: INSIDE})
    agg.close(base + timedelta(minutes=26))

    assert [b.stats.entries for b in got] == [1, 0, 0]
    # occupied time splits across the buckets, summing to ~24 minutes
    total_occ = sum(b.stats.occupied_seconds for b in got)
    assert 23 * 60 <= total_occ <= 25 * 60


def test_wallclock_rejects_bad_bucket_seconds() -> None:
    with pytest.raises(ValueError):
        WallClockAggregator(_wc_zone(), lambda _b: None, bucket_seconds=0)
