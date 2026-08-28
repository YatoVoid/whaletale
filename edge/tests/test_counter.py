from __future__ import annotations

import pytest

from agent.counter import ZoneCounter, percentile
from agent.zones import Zone

INSIDE = (0.5, 0.5)
BAND = (0.5, 0.63)  # outside polygon, inside the exit-margin buffer
CATCHMENT = (0.5, 0.70)  # outside polygon and exit band, inside the catchment
OUTSIDE = (0.5, 0.95)  # outside the catchment too


def make_counter(min_dwell: float = 3.0) -> ZoneCounter:
    z = Zone(
        "sq",
        [(0.4, 0.4), (0.6, 0.4), (0.6, 0.6), (0.4, 0.6)],
        exit_margin=0.05,
        catchment_margin=0.15,
    )
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
    # Person-seconds sums over people: 2 people * 2 seconds.
    assert c.stats.person_seconds == pytest.approx(4.0)
    assert c.stats.peak_occupancy == 2
    assert c.stats.exits == 2  # both left cleanly through the boundary
    assert c.stats.capture_events == c.stats.entries


def test_exit_counted_once_per_clean_boundary_crossing() -> None:
    c = make_counter(min_dwell=0.0)
    for t in (0.0, 1.0, 2.0):
        c.update(t, {1: INSIDE})
    c.update(3.0, {1: OUTSIDE})  # first exit
    for t in (4.0, 5.0, 6.0):
        c.update(t, {1: INSIDE})  # sustained re-entry
    c.update(7.0, {1: OUTSIDE})  # second exit
    c.finalize(8.0)
    assert c.stats.entries == 2
    assert c.stats.exits == 2


def test_track_dropped_while_inside_is_not_an_exit() -> None:
    c = make_counter(min_dwell=0.0)
    for t in (0.0, 1.0, 2.0, 3.0):
        c.update(t, {1: INSIDE})
    c.end_track(1, 4.0)  # tracker lost the id; the person did not leave the zone
    c.finalize(5.0)
    assert c.stats.entries == 1
    assert c.stats.exits == 0


def test_person_seconds_equals_occupied_for_a_lone_visitor() -> None:
    c = make_counter(min_dwell=0.0)
    for t in (0.0, 1.0, 2.0, 3.0):
        c.update(t, {1: INSIDE})
    c.finalize(3.0)
    # One person: person-seconds and occupied seconds coincide. Intervals
    # [1,2] and [2,3]; the track is still PENDING at t=0.
    assert c.stats.occupied_seconds == pytest.approx(2.0)
    assert c.stats.person_seconds == pytest.approx(2.0)


def test_catchment_only_track_is_a_passerby() -> None:
    # Spec 6.4: reaches the catchment, never the zone polygon.
    c = make_counter()
    for t in (0.0, 1.0, 2.0, 3.0):
        c.update(t, {1: CATCHMENT})
    c.finalize(4.0)
    assert c.stats.entries == 0
    assert c.stats.passersby == 1
    assert c.stats.capture_rate == pytest.approx(0.0)


def test_passerby_classified_on_end_track_too() -> None:
    c = make_counter()
    c.update(0.0, {1: CATCHMENT})
    c.update(1.0, {1: CATCHMENT})
    c.end_track(1, 2.0)
    assert c.stats.passersby == 1
    c.finalize(3.0)
    assert c.stats.passersby == 1  # not double-counted


def test_visitor_is_not_also_a_passerby() -> None:
    c = make_counter()
    c.update(0.0, {1: CATCHMENT})  # approaches through the catchment
    for t in (1.0, 2.0, 3.0, 4.0, 5.0):
        c.update(t, {1: INSIDE})
    c.update(6.0, {1: OUTSIDE})
    c.finalize(6.0)
    assert c.stats.entries == 1
    assert c.stats.passersby == 0
    assert c.stats.capture_rate == pytest.approx(1.0)


def test_brief_dip_into_zone_is_neither_entry_nor_passerby() -> None:
    # Under min_dwell so not an entry, but the ground point did enter the
    # polygon, so it is not a passerby either.
    c = make_counter()
    c.update(0.0, {1: CATCHMENT})
    c.update(1.0, {1: INSIDE})
    c.update(2.0, {1: OUTSIDE})
    c.finalize(3.0)
    assert c.stats.entries == 0
    assert c.stats.passersby == 0


def test_capture_rate_with_one_visitor_and_one_passerby() -> None:
    c = make_counter()
    for t in (0.0, 1.0, 2.0, 3.0, 4.0):
        c.update(t, {1: INSIDE, 2: CATCHMENT})
    c.finalize(5.0)
    assert c.stats.entries == 1
    assert c.stats.passersby == 1
    assert c.stats.capture_rate == pytest.approx(0.5)


def test_track_that_never_nears_the_zone_is_ignored() -> None:
    c = make_counter()
    for t in (0.0, 1.0, 2.0):
        c.update(t, {1: OUTSIDE})
    c.finalize(3.0)
    assert c.stats.passersby == 0
    assert c.stats.capture_rate == pytest.approx(0.0)


def make_reentry_counter(min_dwell: float = 0.0) -> ZoneCounter:
    z = Zone(
        "sq",
        [(0.4, 0.4), (0.6, 0.4), (0.6, 0.6), (0.4, 0.6)],
        exit_margin=0.05,
        catchment_margin=0.15,
    )
    return ZoneCounter(z, min_dwell_seconds=min_dwell, reentry_seconds=2.0, reentry_distance=0.06)


def test_occluded_reappearance_is_one_entry() -> None:
    # Spec 8.2: a new track id close in time and space to a just-dropped one is
    # the same person after an occlusion, not a second entry.
    c = make_reentry_counter()
    for t in (0.0, 1.0, 2.0):
        c.update(t, {1: INSIDE})
    assert c.stats.entries == 1
    c.end_track(1, 2.0)  # occlusion: tracker drops the id
    for t in (3.0, 4.0, 5.0):
        c.update(t, {2: INSIDE})  # reappears nearby under a fresh id
    c.update(6.0, {2: OUTSIDE})
    c.finalize(6.0)
    assert c.stats.entries == 1
    assert c.stats.reentries_merged == 1
    assert c.stats.dwell_samples == [pytest.approx(6.0)]  # one visit, t=0..6


def test_new_track_outside_the_window_is_a_fresh_entry() -> None:
    c = make_reentry_counter()
    for t in (0.0, 1.0, 2.0):
        c.update(t, {1: INSIDE})
    c.end_track(1, 2.0)
    for t in (5.0, 6.0, 7.0):  # 3s later, past reentry_seconds=2.0
        c.update(t, {2: INSIDE})
    c.update(8.0, {2: OUTSIDE})
    c.finalize(8.0)
    assert c.stats.entries == 2
    assert c.stats.reentries_merged == 0


def test_new_track_far_away_is_a_fresh_entry() -> None:
    c = make_reentry_counter()
    z2_near = (0.45, 0.45)
    for t in (0.0, 1.0, 2.0):
        c.update(t, {1: z2_near})
    c.end_track(1, 2.0)
    for t in (3.0, 4.0, 5.0):  # in time, but the far corner of the zone
        c.update(t, {2: (0.58, 0.58)})
    c.finalize(6.0)
    assert c.stats.entries == 2
    assert c.stats.reentries_merged == 0


def test_reentry_disabled_by_default_counts_both() -> None:
    c = make_counter(min_dwell=0.0)
    for t in (0.0, 1.0, 2.0):
        c.update(t, {1: INSIDE})
    c.end_track(1, 2.0)
    for t in (3.0, 4.0, 5.0):
        c.update(t, {2: INSIDE})
    c.finalize(6.0)
    assert c.stats.entries == 2


def test_percentile() -> None:
    assert percentile([], 50) == 0.0
    assert percentile([4.0], 90) == 4.0
    assert percentile([1.0, 2.0, 3.0, 4.0], 50) == pytest.approx(2.5)
    assert percentile([1.0, 2.0, 3.0, 4.0], 90) == pytest.approx(3.7)
