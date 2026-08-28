"""Multi-camera capture, one batched inference call per tick, per-zone
aggregation into the SQLite store (spec 6.2).

Each camera decodes in its own thread. PyAV releases the GIL during decode and
torch releases it during inference, so the throughput win the spec calls for -
one inference over frames batched across every stream - is realised here without
a process per camera. True per-camera processes are a later optimisation.
"""

from __future__ import annotations

import threading
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from agent.aggregate import WallClockAggregator, WallClockBucket
from agent.calibration import DriftDetector, RefStore, dhash
from agent.decode import DecodeError, FrozenFrameDetector, decode_frames
from agent.detect import BBoxNorm, Frame
from agent.siteconfig import CameraConfig, SiteConfig
from agent.store import (
    BucketStore,
    CameraHealthRecord,
    ObservationRecord,
    SiteTotalRecord,
)
from agent.track import GroundPointTracker
from agent.zones import ground_point


class Detector(Protocol):
    def detect_batch(self, frames: list[Frame]) -> list[list[tuple[BBoxNorm, float]]]: ...


Clock = Callable[[], datetime]


@dataclass
class _CamAccum:
    """Per-camera counters for the current health window, reset on each flush."""

    frames: int = 0
    score_sum: float = 0.0
    det_count: int = 0
    last_at: datetime | None = None


class _CameraWorker:
    """Decodes one source in a background thread, holding only the newest frame."""

    def __init__(
        self, cam: CameraConfig, fps: float, clock: Clock, *, frozen_after: float = 30.0
    ) -> None:
        self.cam = cam
        self._fps = fps
        self._clock = clock
        self._frozen = FrozenFrameDetector(frozen_after)
        self._lock = threading.Lock()
        self._latest: tuple[datetime, Frame] | None = None
        self._consumed_id = 0
        self._produced_id = 0
        self.error: str | None = None
        self.stopped = False
        self._thread = threading.Thread(target=self._run, name=f"cam-{cam.name}", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def _run(self) -> None:
        try:
            for _t, frame in decode_frames(self.cam.source, self._fps):
                if self._frozen.check(frame, time.monotonic()):
                    self.error = (
                        f"frozen frame: source identical for {self._frozen.after_seconds:.0f}s"
                    )
                    break
                with self._lock:
                    self._latest = (self._clock(), frame)
                    self._produced_id += 1
                if self.stopped:
                    break
        except DecodeError as exc:
            self.error = str(exc)
        finally:
            self.stopped = True

    def take_fresh(self) -> tuple[datetime, Frame] | None:
        """The newest frame if it has not been taken before, else None."""
        with self._lock:
            if self._latest is None or self._produced_id == self._consumed_id:
                return None
            self._consumed_id = self._produced_id
            return self._latest

    def join(self, timeout: float = 5.0) -> None:
        self.stopped = True
        self._thread.join(timeout)


class _ZoneRunner:
    def __init__(
        self,
        camera_name: str,
        zone_version_id: str,
        aggregator: WallClockAggregator,
    ) -> None:
        self.camera_name = camera_name
        self.zone_version_id = zone_version_id
        self.aggregator = aggregator
        self.tracker = GroundPointTracker()
        self._prev_ids: set[int] = set()

    def process(self, captured_at: datetime, dets: list[tuple[BBoxNorm, float]]) -> None:
        gps = [ground_point(box) for box, _score in dets]
        live = self.tracker.update(gps)
        for lost in self._prev_ids - live.keys():
            self.aggregator.end_track(lost, captured_at)
        self.aggregator.update(captured_at, live)
        self._prev_ids = set(live)


class MultiCameraPipeline:
    def __init__(
        self,
        site: SiteConfig,
        detector: Detector,
        store: BucketStore,
        *,
        fps: float = 4.0,
        min_dwell_seconds: float = 3.0,
        exit_margin: float = 0.02,
        catchment_margin: float = 0.08,
        bucket_seconds: int = 900,
        reentry_seconds: float = 0.0,
        reentry_distance: float = 0.0,
        frozen_frame_seconds: float = 30.0,
        health_flush_seconds: float = 60.0,
        ref_dir: str | None = None,
        recalibration_check_seconds: float = 3600.0,
        drift_hamming_threshold: int = 12,
        drift_samples: int = 2,
        clock: Clock | None = None,
    ) -> None:
        self.site = site
        self.detector = detector
        self.store = store
        self._clock: Clock = clock or (lambda: datetime.now(UTC))
        self._fps = fps

        self._health_flush_seconds = health_flush_seconds
        self._cam_accum: dict[str, _CamAccum] = {c.name: _CamAccum() for c in site.cameras}
        self._health_window_start = time.monotonic()
        self._last_health_flush = time.monotonic()

        # spec 8.1: perceptual-hash drift detection. Missing ref_dir disables it.
        self._refstore = RefStore(ref_dir) if ref_dir else None
        self._drift_threshold = drift_hamming_threshold
        self._drift_samples = drift_samples
        self._recalib_check_seconds = recalibration_check_seconds
        self._last_recalib_check = time.monotonic()
        self._drift: dict[str, DriftDetector] = {}
        self._recalib_flagged: set[str] = set()
        if self._refstore is not None:
            for c in site.cameras:
                self._drift[c.name] = DriftDetector(
                    self._refstore.get(c.name),
                    threshold=drift_hamming_threshold,
                    samples_needed=drift_samples,
                )

        # site-total bookkeeping, keyed by bucket start
        self._site_entries: Counter[datetime] = Counter()
        self._site_cameras: dict[datetime, set[str]] = {}
        self._site_written: set[datetime] = set()

        self._runners: list[_ZoneRunner] = []
        for cam in site.cameras:
            for zc in cam.zones:
                zone = zc.build_zone(exit_margin=exit_margin, catchment_margin=catchment_margin)
                runner = _ZoneRunner(
                    cam.name,
                    zc.zone_version_id,
                    WallClockAggregator(
                        zone,
                        self._make_on_bucket(cam.name, zc.zone_version_id),
                        min_dwell_seconds=min_dwell_seconds,
                        bucket_seconds=bucket_seconds,
                        reentry_seconds=reentry_seconds,
                        reentry_distance=reentry_distance,
                    ),
                )
                self._runners.append(runner)

        self._workers = [
            _CameraWorker(cam, fps, self._clock, frozen_after=frozen_frame_seconds)
            for cam in site.cameras
        ]
        self._runners_by_cam: dict[str, list[_ZoneRunner]] = {}
        for r in self._runners:
            self._runners_by_cam.setdefault(r.camera_name, []).append(r)

    def _make_on_bucket(
        self, camera_name: str, zone_version_id: str
    ) -> Callable[[WallClockBucket], None]:
        def on_bucket(b: WallClockBucket) -> None:
            s = b.stats
            self.store.write_observation(
                ObservationRecord(
                    zone_version_id=zone_version_id,
                    bucket_start=b.start,
                    bucket_end=b.end,
                    entries=s.entries,
                    exits=s.exits,
                    peak_occupancy=s.peak_occupancy,
                    occupied_seconds=round(s.occupied_seconds, 1),
                    dwell_p50_seconds=round(s.dwell_p50, 1),
                    dwell_p90_seconds=round(s.dwell_p90, 1),
                    passersby=s.passersby,
                    capture_events=s.capture_events,
                )
            )
            self._site_entries[b.start] += s.entries
            self._site_cameras.setdefault(b.start, set()).add(camera_name)
            self._write_completed_site_totals(before=b.start)

        return on_bucket

    def _write_completed_site_totals(self, *, before: datetime) -> None:
        for bstart in sorted(self._site_entries):
            if bstart >= before or bstart in self._site_written:
                continue
            self._flush_site_total(bstart)

    def _flush_site_total(self, bstart: datetime) -> None:
        self.store.write_site_total(
            SiteTotalRecord(
                site_id=self.site.site_id,
                bucket_start=bstart,
                total_people=self._site_entries[bstart],
                active_cameras=len(self._site_cameras.get(bstart, set())),
            )
        )
        self._site_written.add(bstart)

    def run(self, stop: Callable[[], bool]) -> None:
        for w in self._workers:
            w.start()
        while not stop():
            batch: list[tuple[_CameraWorker, datetime, Frame]] = []
            for w in self._workers:
                fresh = w.take_fresh()
                if fresh is not None:
                    batch.append((w, fresh[0], fresh[1]))
            if not batch:
                if all(w.stopped for w in self._workers):
                    break
                continue
            drift_sweep = (
                self._refstore is not None
                and time.monotonic() - self._last_recalib_check >= self._recalib_check_seconds
            )
            results = self.detector.detect_batch([f for _w, _t, f in batch])
            for (w, captured_at, frame), dets in zip(batch, results, strict=True):
                if drift_sweep:
                    self._check_drift(w.cam.name, frame)
                acc = self._cam_accum[w.cam.name]
                acc.frames += 1
                acc.last_at = captured_at
                if w.cam.name in self._recalib_flagged:
                    continue  # camera moved: stop counting rather than count wrong
                acc.det_count += len(dets)
                acc.score_sum += sum(score for _b, score in dets)
                for runner in self._runners_by_cam.get(w.cam.name, []):
                    runner.process(captured_at, dets)
            if drift_sweep:
                self._last_recalib_check = time.monotonic()
            if time.monotonic() - self._last_health_flush >= self._health_flush_seconds:
                self._flush_camera_health()

    def _check_drift(self, camera_name: str, frame: Frame) -> None:
        assert self._refstore is not None
        h = dhash(frame)
        det = self._drift.get(camera_name)
        if det is None or det.reference is None:
            self._refstore.set(camera_name, h)  # first clean view: capture the reference
            self._drift[camera_name] = DriftDetector(
                h, threshold=self._drift_threshold, samples_needed=self._drift_samples
            )
            return
        if det.feed(h):
            self._recalib_flagged.add(camera_name)

    def _flush_camera_health(self) -> None:
        elapsed = max(1e-6, time.monotonic() - self._health_window_start)
        for w in self._workers:
            acc = self._cam_accum[w.cam.name]
            mc = acc.score_sum / acc.det_count if acc.det_count else None
            if w.error and "frozen" in w.error:
                status = "frozen"
            elif w.cam.name in self._recalib_flagged:
                status = "needs_recalibration"
            elif w.error or acc.frames == 0:
                status = "offline"
            else:
                status = "online"
            self.store.write_camera_health(
                CameraHealthRecord(
                    camera_name=w.cam.name,
                    status=status,
                    fps_actual=round(acc.frames / elapsed, 2),
                    mean_confidence=round(mc, 4) if mc is not None else None,
                    last_frame_at=acc.last_at,
                )
            )
            acc.frames = 0
            acc.score_sum = 0.0
            acc.det_count = 0
        self._health_window_start = time.monotonic()
        self._last_health_flush = time.monotonic()

    def close(self) -> None:
        for w in self._workers:
            w.join()
        now = self._clock()
        for runner in self._runners:
            runner.aggregator.close(now)
        for bstart in sorted(self._site_entries):
            if bstart not in self._site_written:
                self._flush_site_total(bstart)
        self._flush_camera_health()

    @property
    def worker_errors(self) -> dict[str, str]:
        return {w.cam.name: w.error for w in self._workers if w.error}
