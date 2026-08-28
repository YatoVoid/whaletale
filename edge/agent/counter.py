from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

from agent.zones import Zone


class _State(Enum):
    OUTSIDE = auto()
    PENDING = auto()  # inside the polygon but not yet past min_dwell
    INSIDE = auto()  # counted as an entry


@dataclass
class _TrackState:
    state: _State = _State.OUTSIDE
    first_inside_t: float = 0.0  # when the ground point first crossed in
    pending_since: float = 0.0
    entered_polygon: bool = False  # ground point was inside the zone polygon at least once
    seen_in_catchment: bool = False  # ground point reached the zone's catchment
    last_gp: tuple[float, float] = (0.0, 0.0)  # most recent ground point


def percentile(values: list[float], q: float) -> float:
    """Linear-interpolated percentile. q in 0..100. Empty -> 0.0."""
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    pos = (q / 100.0) * (len(s) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


@dataclass
class ZoneStats:
    entries: int = 0
    exits: int = 0  # clean outside transitions through the boundary (spec 5.1)
    peak_occupancy: int = 0  # max concurrent people inside during the bucket (spec 5.1)
    passersby: int = 0
    occupied_seconds: float = 0.0
    person_seconds: float = 0.0  # spec 6.4: sum over people of time inside, != occupied
    dwell_samples: list[float] = field(default_factory=list)
    reentries_merged: int = 0  # spec 8.2: track fragments stitched back together

    @property
    def dwell_p50(self) -> float:
        return percentile(self.dwell_samples, 50)

    @property
    def dwell_p90(self) -> float:
        return percentile(self.dwell_samples, 90)

    @property
    def capture_events(self) -> int:
        """spec 5.1: the stored numerator for capture rate. On the edge every
        entry counts, so this equals `entries`."""
        return self.entries

    @property
    def capture_rate(self) -> float:
        """spec 6.4: entries / (entries + passersby). 0.0 when nobody came near."""
        denom = self.entries + self.passersby
        return self.entries / denom if denom else 0.0


class ZoneCounter:
    """Per-zone entry / occupancy / dwell / passerby accounting.

    Metric definitions are spec 6.4 and must not drift. Feed it one call per
    processed frame with the current live tracks; call `end_track` when the
    tracker drops an id, and `finalize` once at end of stream.

    A track is classified as a passerby when it is removed: it reached the
    zone's catchment but its ground point never entered the zone polygon.

    Spec 8.2 re-entry grace window: an occluded person reappears under a fresh
    track id, which would otherwise read as a second entry. When
    `reentry_seconds` and `reentry_distance` are both > 0, a dropped track is
    parked briefly; a new track that starts within that time and distance
    inherits its state instead of opening a new visit.
    """

    def __init__(
        self,
        zone: Zone,
        min_dwell_seconds: float = 3.0,
        *,
        reentry_seconds: float = 0.0,
        reentry_distance: float = 0.0,
    ) -> None:
        self.zone = zone
        self.min_dwell_seconds = min_dwell_seconds
        self.reentry_seconds = reentry_seconds
        self.reentry_distance = reentry_distance
        self.stats = ZoneStats()
        self._tracks: dict[int, _TrackState] = {}
        self._parked: dict[int, tuple[_TrackState, float]] = {}  # tid -> (state, dropped_at)
        self._last_t: float | None = None
        self._inside_count = 0  # tracks in INSIDE state as of _last_t

    @property
    def _reentry_enabled(self) -> bool:
        return self.reentry_seconds > 0.0 and self.reentry_distance > 0.0

    def accrue_to(self, t: float) -> None:
        """Attribute the interval [_last_t, t] to the occupancy that held at
        _last_t (no lookahead), without advancing any track. The aggregator
        calls this at a bucket boundary so time-based metrics split cleanly
        while entries and dwell stay attributed to the bucket they resolve in."""
        if self._last_t is not None:
            dt = t - self._last_t
            if dt > 0 and self._inside_count:
                self.stats.occupied_seconds += dt
                self.stats.person_seconds += dt * self._inside_count
        self._last_t = t

    def update(self, t: float, ground_points: dict[int, tuple[float, float]]) -> None:
        """`ground_points`: {track_id: (x, y)} for every currently live track."""
        self.accrue_to(t)

        for tid, gp in ground_points.items():
            self._advance(tid, gp, t)

        self._expire_parked(t)
        self._inside_count = sum(1 for ts in self._tracks.values() if ts.state is _State.INSIDE)
        self.stats.peak_occupancy = max(self.stats.peak_occupancy, self._inside_count)

    def _advance(self, tid: int, gp: tuple[float, float], t: float) -> None:
        ts = self._tracks.get(tid)
        if ts is None:
            ts = self._claim_parked(gp, t) or _TrackState()
            self._tracks[tid] = ts
        ts.last_gp = gp

        inside_enter = self.zone.contains_enter(gp)
        inside_stay = self.zone.contains_stay(gp)
        if inside_enter:
            ts.entered_polygon = True
        if self.zone.contains_catchment(gp):
            ts.seen_in_catchment = True

        if ts.state is _State.OUTSIDE:
            if inside_enter:
                ts.state = _State.PENDING
                ts.pending_since = t
                ts.first_inside_t = t
        elif ts.state is _State.PENDING:
            if inside_stay:
                if t - ts.pending_since >= self.min_dwell_seconds:
                    ts.state = _State.INSIDE
                    self.stats.entries += 1
            else:
                ts.state = _State.OUTSIDE
        elif ts.state is _State.INSIDE and not inside_stay:
            self.stats.dwell_samples.append(t - ts.first_inside_t)
            self.stats.exits += 1
            ts.state = _State.OUTSIDE

    def _claim_parked(self, gp: tuple[float, float], t: float) -> _TrackState | None:
        """spec 8.2: a fresh track id near a just-dropped one is the same person
        reappearing after an occlusion. Reuse the parked state so the visit is
        not counted twice."""
        if not self._reentry_enabled:
            return None
        best: tuple[int, float] | None = None
        for ptid, (pstate, dropped_at) in self._parked.items():
            if t - dropped_at > self.reentry_seconds:
                continue
            d = _dist(gp, pstate.last_gp)
            if d <= self.reentry_distance and (best is None or d < best[1]):
                best = (ptid, d)
        if best is None:
            return None
        state, _ = self._parked.pop(best[0])
        if state.state in (_State.PENDING, _State.INSIDE):
            self.stats.reentries_merged += 1
        return state

    def _expire_parked(self, t: float) -> None:
        stale = [
            tid
            for tid, (_, dropped_at) in self._parked.items()
            if t - dropped_at > self.reentry_seconds
        ]
        for tid in stale:
            state, dropped_at = self._parked.pop(tid)
            # classify at the drop time, not now: the grace window has expired
            # without a re-entry, so the visit really ended when the track did.
            self._classify_on_remove(state, dropped_at)

    def _classify_on_remove(self, ts: _TrackState, t: float) -> None:
        if ts.state is _State.INSIDE:
            self.stats.dwell_samples.append(t - ts.first_inside_t)
        if ts.seen_in_catchment and not ts.entered_polygon:
            self.stats.passersby += 1

    def end_track(self, tid: int, t: float) -> None:
        ts = self._tracks.pop(tid, None)
        if ts is None:
            return
        if self._reentry_enabled:
            self._parked[tid] = (ts, t)
        else:
            self._classify_on_remove(ts, t)

    def finalize(self, t: float) -> None:
        self.accrue_to(t)
        for ts, dropped_at in self._parked.values():
            self._classify_on_remove(ts, dropped_at)
        self._parked.clear()
        for ts in self._tracks.values():
            self._classify_on_remove(ts, t)
        self._tracks.clear()


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return float(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5)
