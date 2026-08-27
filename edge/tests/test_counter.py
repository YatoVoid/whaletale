from __future__ import annotations

import pytest

from agent.counter import ZoneCounter, percentile
from agent.zones import Zone

INSIDE = (0.5, 0.5)
BAND = (0.5, 0.63)  # outside polygon, inside the exit-margin buffer
OUTSIDE = (0.5, 0.85)


def make_counter(min_dwell: float = 3.0) -> ZoneCounter:
    z = Zone("sq", [(0.4, 0.4), (0.6, 0.4), (0.6, 0.6), (0.4, 0.6)], exit_margin=0.05)
    return ZoneCounter(z, min_dwell_seconds=min_dwell)


def test_brief_boundary_touch_is_not_an_entry() -> None:
    # Spec 6.4: must remain inside >= min_dwell_seconds. Jitter is suppressed.
    c = make_counter()
    c.update(0.0, {1: INSIDE})
    c.update(1.0, {1: OUTSIDE})
    c.finalize(1.0)
    assert c.stats.entries == 0
    assert c.stats.dwell_samples == []


def test_sustained_presence_counts_one_entry() -> None:
    c = make_counter()
    for t in (0.0, 1.0, 2.0, 3.0, 4.0):
        c.update(t, {1: INSIDE})
    c.update(5.0, {1: OUTSIDE})
    c.finalize(5.0)
    assert c.stats.entries == 1  # counted once, not per frame
    assert c.stats.occupied_seconds == pytest.approx(2.0)  # intervals [3,4] and [4,5]
    assert c.stats.dwell_samples == [pytest.approx(5.0)]  # from first-inside at t=0


def test_loitering_on_boundary_does_not_double_count() -> None:
    # Spec 8.2: min_dwell plus hysteresis (separate enter / exit thresholds).
    c = make_counter()
    for t in (0.0, 1.0, 2.0, 3.0):
        c.update(t, {1: INSIDE})
    assert c.stats.entries == 1
    # Now hover in the hysteresis band: not "inside" for a fresh entry, but not
    # "outside" enough to end the visit either.
    for t in (4.0, 5.0, 6.0, 7.0):
        c.update(t, {1: BAND})
    assert c.stats.entries == 1
    assert c.stats.dwell_samples == []  # visit still open
    c.update(8.0, {1: OUTSIDE})
    c.finalize(8.0)
    assert c.stats.entries == 1
    assert c.stats.dwell_samples == [pytest.approx(8.0)]


def test_finalize_closes_dwell_for_a_track_still_inside() -> None:
    c = make_counter()
    for t in (0.0, 1.0, 2.0, 3.0, 4.0):
        c.update(t, {1: INSIDE})
    c.finalize(10.0)  # stream ends with the person still in the zone
    assert c.stats.dwell_samples == [pytest.approx(10.0)]
    assert c.stats.dwell_p50 == pytest.approx(10.0)
    assert c.stats.dwell_p90 == pytest.approx(10.0)


def test_end_track_closes_open_dwell() -> None:
    c = make_counter()
    for t in (0.0, 1.0, 2.0, 3.0, 4.0):
        c.update(t, {7: INSIDE})
    c.end_track(7, 6.0)  # tracker dropped the id while still inside
    assert c.stats.dwell_samples == [pytest.approx(6.0)]
    c.finalize(6.0)
    assert c.stats.dwell_samples == [pytest.approx(6.0)]  # not double-recorded


def test_two_people_one_zone_occupied_is_wall_clock_not_sum() -> None:
    # Spec 6.4: occupied seconds is wall-clock with >=1 person, not person-seconds.
    c = make_counter(min_dwell=0.0)
    # PENDING -> INSIDE resolves on the next frame, so both are counted at t=1.
    c.update(0.0, {1: INSIDE, 2: INSIDE})
    c.update(1.0, {1: INSIDE, 2: INSIDE})
    c.update(2.0, {1: INSIDE, 2: INSIDE})
    c.update(3.0, {1: OUTSIDE, 2: OUTSIDE})
    c.finalize(3.0)
    assert c.stats.entries == 2
    # Both inside for the intervals [1,2] and [2,3]; wall-clock, not 4.0.
    assert c.stats.occupied_seconds == pytest.approx(2.0)


def test_percentile() -> None:
    assert percentile([], 50) == 0.0
    assert percentile([4.0], 90) == 4.0
    assert percentile([1.0, 2.0, 3.0, 4.0], 50) == pytest.approx(2.5)
    assert percentile([1.0, 2.0, 3.0, 4.0], 90) == pytest.approx(3.7)
