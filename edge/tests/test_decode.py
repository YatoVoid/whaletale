from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import av
import numpy as np
import pytest

from agent import decode
from agent.decode import (
    DecodeError,
    Frame,
    FrozenFrameDetector,
    decode_frames,
    is_live_source,
    source_spec,
)


def test_frozen_frame_detector_trips_only_after_the_threshold() -> None:
    d = FrozenFrameDetector(after_seconds=30.0)
    a = np.zeros((8, 8, 3), dtype=np.uint8)
    assert d.check(a, now=0.0) is False  # first frame
    assert d.check(a.copy(), now=10.0) is False  # first repeat: the freeze clock starts here
    assert d.check(a.copy(), now=39.9) is False  # 29.9s frozen
    assert d.check(a.copy(), now=40.0) is True  # 30s frozen, past the threshold


def test_frozen_frame_detector_resets_on_a_changed_frame() -> None:
    d = FrozenFrameDetector(after_seconds=5.0)
    a = np.zeros((4, 4, 3), dtype=np.uint8)
    b = np.ones((4, 4, 3), dtype=np.uint8)
    d.check(a, now=0.0)
    assert d.check(a.copy(), now=4.0) is False  # freeze clock starts at 4.0
    assert d.check(b, now=6.0) is False  # scene changed, clock resets
    assert d.check(b.copy(), now=10.0) is False  # new freeze clock starts at 10.0
    assert d.check(b.copy(), now=15.0) is True  # 5s into the new freeze


def test_webcam_index_maps_to_v4l2_device() -> None:
    url, fmt, options = source_spec("0")
    assert url == "/dev/video0"
    assert fmt == "v4l2"
    assert options == {}


def test_rtsp_forces_tcp_transport() -> None:
    url, fmt, options = source_spec("rtsp://cam.local/stream1")
    assert url == "rtsp://cam.local/stream1"
    assert fmt is None
    assert options["rtsp_transport"] == "tcp"
    assert "timeout" in options


def test_http_stream_gets_a_socket_timeout() -> None:
    url, fmt, options = source_spec("http://host/live.m3u8")
    assert url == "http://host/live.m3u8"
    assert fmt is None
    assert options == {"timeout": "10000000"}


def test_file_path_passes_through() -> None:
    url, fmt, options = source_spec("/data/clip.mp4")
    assert url == "/data/clip.mp4"
    assert fmt is None
    assert options == {}


@pytest.mark.parametrize(
    ("source", "live"),
    [
        ("0", True),
        ("rtsp://cam/stream", True),
        ("http://host/stream.m3u8", True),
        ("/data/clip.mp4", False),
        ("clip.mp4", False),
    ],
)
def test_is_live_source(source: str, live: bool) -> None:
    assert is_live_source(source) is live


def _write_clip(path: Path, n_frames: int, rate: int) -> None:
    container = av.open(str(path), "w")
    stream = container.add_stream("mpeg4", rate=rate)
    stream.width, stream.height, stream.pix_fmt = 64, 48, "yuv420p"
    for i in range(n_frames):
        arr = np.full((48, 64, 3), (i * 8) % 256, dtype=np.uint8)
        for pkt in stream.encode(av.VideoFrame.from_ndarray(arr, format="rgb24")):
            container.mux(pkt)
    for pkt in stream.encode():
        container.mux(pkt)
    container.close()


def test_decode_frames_decimates_to_target_fps(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mp4"
    _write_clip(clip, n_frames=30, rate=15)  # 2 seconds of source

    out = list(decode_frames(str(clip), target_fps=5.0))

    assert len(out) == 10  # 2s * 5fps
    timestamps = [t for t, _ in out]
    assert timestamps == sorted(timestamps)
    assert timestamps[0] == pytest.approx(0.0)
    assert all(0.0 <= t < 2.1 for t in timestamps)
    frame = out[0][1]
    assert frame.shape == (48, 64, 3)
    assert frame.dtype == np.uint8


def test_missing_file_raises_decode_error(tmp_path: Path) -> None:
    with pytest.raises(DecodeError):
        list(decode_frames(str(tmp_path / "nope.mp4"), target_fps=4.0))


def test_file_decode_failure_is_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: object, **_k: object) -> Iterator[tuple[float, Frame]]:
        yield 0.0, np.zeros((1, 1, 3), dtype=np.uint8)
        raise av.FFmpegError(1, "corrupt")

    monkeypatch.setattr(decode, "_open", lambda *_a, **_k: _FakeContainer())
    monkeypatch.setattr(decode, "_decode_once", boom)

    it = decode_frames("clip.mp4", target_fps=4.0)
    t, _ = next(it)
    assert t == 0.0
    with pytest.raises(DecodeError, match="decode failed"):
        list(it)


def test_live_source_gives_up_after_max_reconnects(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: object, **_k: object) -> Iterator[tuple[float, object]]:
        raise av.FFmpegError(1, "connection reset")
        yield  # unreachable, makes this a generator

    monkeypatch.setattr(decode, "_open", lambda *_a, **_k: _FakeContainer())
    monkeypatch.setattr(decode, "_decode_once", boom)

    with pytest.raises(DecodeError, match="reconnect attempts"):
        list(decode_frames("rtsp://cam/stream", target_fps=4.0, max_reconnects=2, backoff_base=0.0))


def test_live_source_clean_eof_also_reconnects(monkeypatch: pytest.MonkeyPatch) -> None:
    def empty(*_a: object, **_k: object) -> Iterator[tuple[float, Frame]]:
        return iter(())

    monkeypatch.setattr(decode, "_open", lambda *_a, **_k: _FakeContainer())
    monkeypatch.setattr(decode, "_decode_once", empty)

    with pytest.raises(DecodeError, match="did not recover"):
        list(decode_frames("rtsp://cam/stream", target_fps=4.0, max_reconnects=1, backoff_base=0.0))


class _FakeContainer:
    def close(self) -> None:
        pass
