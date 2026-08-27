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
    occupied_seconds: float = 0.0
    dwell_samples: list[float] = field(default_factory=list)

    @property
    def dwell_p50(self) -> float:
        return percentile(self.dwell_samples, 50)

    @property
    def dwell_p90(self) -> float:
        return percentile(self.dwell_samples, 90)


class ZoneCounter:
    """Per-zone entry / occupancy / dwell accounting.

    Metric definitions are spec 6.4 and must not drift. Feed it one call per
    processed frame with the current live tracks; call `end_track` when the
    tracker drops an id, and `finalize` once at end of stream.
    """

    def __init__(self, zone: Zone, min_dwell_seconds: float = 3.0) -> None:
        self.zone = zone
        self.min_dwell_seconds = min_dwell_seconds
        self.stats = ZoneStats()
        self._tracks: dict[int, _TrackState] = {}
        self._last_t: float | None = None
        self._occupied = False

    def update(self, t: float, ground_points: dict[int, tuple[float, float]]) -> None:
        """`ground_points`: {track_id: (x, y)} for every currently live track."""
        if self._last_t is not None:
            dt = t - self._last_t
            if dt > 0 and self._occupied:
                # Attribute the interval [last_t, t] to the occupancy state that
                # held at last_t (no lookahead).
                self.stats.occupied_seconds += dt
        self._last_t = t

        for tid, gp in ground_points.items():
            self._advance(tid, gp, t)

        self._occupied = any(ts.state is _State.INSIDE for ts in self._tracks.values())

    def _advance(self, tid: int, gp: tuple[float, float], t: float) -> None:
        ts = self._tracks.get(tid)
        if ts is None:
            ts = _TrackState()
            self._tracks[tid] = ts

        inside_enter = self.zone.contains_enter(gp)
        inside_stay = self.zone.contains_stay(gp)

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
            ts.state = _State.OUTSIDE

    def end_track(self, tid: int, t: float) -> None:
        ts = self._tracks.pop(tid, None)
        if ts is not None and ts.state is _State.INSIDE:
            self.stats.dwell_samples.append(t - ts.first_inside_t)

    def finalize(self, t: float) -> None:
        if self._last_t is not None:
            dt = t - self._last_t
            if dt > 0 and self._occupied:
                self.stats.occupied_seconds += dt
        for ts in self._tracks.values():
            if ts.state is _State.INSIDE:
                self.stats.dwell_samples.append(t - ts.first_inside_t)
        self._tracks.clear()
