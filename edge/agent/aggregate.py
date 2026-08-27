from __future__ import annotations

from dataclasses import dataclass

from agent.counter import ZoneCounter, ZoneStats
from agent.zones import Zone


@dataclass(frozen=True)
class Bucket:
    index: int  # 0-based bucket number from stream start
    start: float  # stream-time seconds, inclusive
    end: float  # stream-time seconds, exclusive
    stats: ZoneStats


class RunAggregator:
    """Splits a run into fixed stream-time buckets (spec 6.5).

    Track state is continuous across boundaries: one `ZoneCounter` runs the
    whole stream, and its `stats` object is swapped out at each boundary. Time
    metrics (occupied, person-seconds) split at the boundary; event metrics
    (entries, dwell samples, passersby) land in the bucket where they resolve.

    Feed `update` one call per processed frame, then `finalize` once.
    """

    def __init__(self, zone: Zone, min_dwell_seconds: float, bucket_seconds: float) -> None:
        if bucket_seconds <= 0:
            raise ValueError(f"bucket_seconds must be > 0, got {bucket_seconds}")
        self.zone = zone
        self.bucket_seconds = bucket_seconds
        self._counter = ZoneCounter(zone, min_dwell_seconds=min_dwell_seconds)
        self._buckets: list[Bucket] = []
        self._bucket_index = 0
        self._bucket_start = 0.0
        self._started = False

    def _roll_to(self, t: float) -> None:
        if not self._started:
            return
        while t >= self._bucket_start + self.bucket_seconds:
            boundary = self._bucket_start + self.bucket_seconds
            self._counter.accrue_to(boundary)
            self._buckets.append(
                Bucket(self._bucket_index, self._bucket_start, boundary, self._counter.stats)
            )
            self._counter.stats = ZoneStats()
            self._bucket_index += 1
            self._bucket_start = boundary

    def update(self, t: float, ground_points: dict[int, tuple[float, float]]) -> None:
        if not self._started:
            self._bucket_start = t - (t % self.bucket_seconds)
            self._bucket_index = 0
            self._started = True
        self._roll_to(t)
        self._counter.update(t, ground_points)

    def end_track(self, tid: int, t: float) -> None:
        self._roll_to(t)
        self._counter.end_track(tid, t)

    def finalize(self, t: float) -> list[Bucket]:
        if not self._started:
            return []
        self._roll_to(t)
        self._counter.finalize(t)
        self._buckets.append(
            Bucket(
                self._bucket_index,
                self._bucket_start,
                max(t, self._bucket_start),
                self._counter.stats,
            )
        )
        return self._buckets

    @property
    def buckets(self) -> list[Bucket]:
        return self._buckets

    @property
    def entries_so_far(self) -> int:
        """Entries across completed buckets plus the one in progress (for a
        live progress line)."""
        return sum(b.stats.entries for b in self._buckets) + self._counter.stats.entries

    def totals(self) -> ZoneStats:
        """Run-wide totals, summed across finalized buckets."""
        out = ZoneStats()
        for b in self._buckets:
            out.entries += b.stats.entries
            out.passersby += b.stats.passersby
            out.occupied_seconds += b.stats.occupied_seconds
            out.person_seconds += b.stats.person_seconds
            out.dwell_samples.extend(b.stats.dwell_samples)
        return out
