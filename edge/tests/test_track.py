from __future__ import annotations

from agent.track import GroundPointTracker


def test_stable_id_for_a_moving_point() -> None:
    t = GroundPointTracker(distance_threshold=0.1)
    ids: set[int] = set()
    # initialization_delay=2 -> needs a few consistent hits before it reports.
    for i in range(8):
        live = t.update([(0.2 + i * 0.02, 0.5)])
        ids.update(live)
    assert len(ids) == 1  # one person, one id, no churn


def test_dropped_detection_ends_the_track() -> None:
    t = GroundPointTracker(distance_threshold=0.1)
    for i in range(8):
        t.update([(0.3 + i * 0.01, 0.6)])
    seen_before = set(t.update([(0.4, 0.6)]))
    assert seen_before
    # No detections for longer than hit_counter_max frames -> track goes away.
    last: dict[int, tuple[float, float]] = {}
    for _ in range(30):
        last = t.update([])
    assert last == {}
