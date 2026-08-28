from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import av
import numpy as np

from agent.detect import BBoxNorm, Frame
from agent.pipeline import MultiCameraPipeline
from agent.siteconfig import parse_site_config
from agent.store import BucketStore

ZONE_POLY = [[0.3, 0.4], [0.7, 0.4], [0.7, 0.9], [0.3, 0.9]]
PERSON_BOX: BBoxNorm = (0.45, 0.40, 0.55, 0.62)  # ground point ~ (0.5, 0.62), inside


class _AlwaysOnePerson:
    def detect_batch(self, frames: list[Frame]) -> list[list[tuple[BBoxNorm, float]]]:
        return [[(PERSON_BOX, 0.95)] for _ in frames]


class _FakeClock:
    def __init__(self, base: datetime) -> None:
        self.now = base

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


def _write_clip(path: Path, n_frames: int, rate: int) -> None:
    container = av.open(str(path), "w")
    stream = container.add_stream("mpeg4", rate=rate)
    stream.width, stream.height, stream.pix_fmt = 64, 48, "yuv420p"
    for i in range(n_frames):
        arr = np.full((48, 64, 3), (i * 4) % 256, dtype=np.uint8)
        for pkt in stream.encode(av.VideoFrame.from_ndarray(arr, format="rgb24")):
            container.mux(pkt)
    for pkt in stream.encode():
        container.mux(pkt)
    container.close()


def _config(clip_a: Path, clip_b: Path) -> object:
    return parse_site_config(
        {
            "site_id": "site-1",
            "cloud_url": "https://example.test",
            "pairing_token": "tok",
            "cameras": [
                {
                    "name": "cam-a",
                    "source": str(clip_a),
                    "zones": [{"zone_version_id": "zv-a", "polygon": ZONE_POLY}],
                },
                {
                    "name": "cam-b",
                    "source": str(clip_b),
                    "zones": [{"zone_version_id": "zv-b", "polygon": ZONE_POLY}],
                },
            ],
        }
    )


def test_frozen_stream_surfaces_a_worker_error(tmp_path: Path) -> None:
    # spec 8.1: a source that keeps delivering the same frame is offline.
    clip = tmp_path / "frozen.nut"
    container = av.open(str(clip), "w")
    stream = container.add_stream("rawvideo", rate=15)  # lossless: decoded frames are exact
    stream.width, stream.height, stream.pix_fmt = 64, 48, "rgb24"
    still = np.full((48, 64, 3), 120, dtype=np.uint8)
    for _ in range(60):
        for pkt in stream.encode(av.VideoFrame.from_ndarray(still, format="rgb24")):
            container.mux(pkt)
    for pkt in stream.encode():
        container.mux(pkt)
    container.close()

    store = BucketStore(tmp_path / "edge.db")
    pipeline = MultiCameraPipeline(
        _config(clip, clip),  # type: ignore[arg-type]
        _AlwaysOnePerson(),
        store,
        fps=4.0,
        min_dwell_seconds=0.0,
        bucket_seconds=5,
        frozen_frame_seconds=0.0,  # trip on the first repeated frame
        clock=_FakeClock(datetime(2026, 6, 1, 12, 0, tzinfo=UTC)),
    )
    pipeline.run(stop=lambda: False)
    pipeline.close()

    assert any("frozen frame" in e for e in pipeline.worker_errors.values())
    store.close()


def test_two_cameras_write_observations_and_a_site_total(tmp_path: Path) -> None:
    clip_a, clip_b = tmp_path / "a.mp4", tmp_path / "b.mp4"
    _write_clip(clip_a, n_frames=90, rate=15)  # 6 s
    _write_clip(clip_b, n_frames=90, rate=15)

    store = BucketStore(tmp_path / "edge.db")
    pipeline = MultiCameraPipeline(
        _config(clip_a, clip_b),  # type: ignore[arg-type]
        _AlwaysOnePerson(),
        store,
        fps=4.0,
        min_dwell_seconds=0.0,
        bucket_seconds=5,
        clock=_FakeClock(datetime(2026, 6, 1, 12, 0, tzinfo=UTC)),
    )
    pipeline.run(stop=lambda: False)
    pipeline.close()

    obs = store.unsynced_observations()
    zvs = {o["zone_version_id"] for o in obs}
    assert zvs == {"zv-a", "zv-b"}
    assert sum(o["entries"] for o in obs) >= 2  # at least one entry per camera
    assert all(o["peak_occupancy"] >= 1 for o in obs if o["entries"])

    totals = store.unsynced_site_totals()
    assert totals
    assert max(t["active_cameras"] for t in totals) == 2
    assert sum(t["total_people"] for t in totals) == sum(o["entries"] for o in obs)
    assert not pipeline.worker_errors
    store.close()


def test_a_dead_source_is_recorded_not_raised(tmp_path: Path) -> None:
    clip_a = tmp_path / "a.mp4"
    _write_clip(clip_a, n_frames=60, rate=15)
    store = BucketStore(tmp_path / "edge.db")
    pipeline = MultiCameraPipeline(
        _config(clip_a, tmp_path / "missing.mp4"),  # type: ignore[arg-type]
        _AlwaysOnePerson(),
        store,
        fps=4.0,
        min_dwell_seconds=0.0,
        bucket_seconds=5,
        clock=_FakeClock(datetime(2026, 6, 1, 12, 0, tzinfo=UTC)),
    )
    pipeline.run(stop=lambda: False)
    pipeline.close()

    assert "cam-b" in pipeline.worker_errors
    assert {o["zone_version_id"] for o in store.unsynced_observations()} == {"zv-a"}
    store.close()
