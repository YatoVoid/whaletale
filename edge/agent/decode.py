from __future__ import annotations

import time
from collections.abc import Iterator
from typing import cast

import av
import numpy as np
import numpy.typing as npt

Frame = npt.NDArray[np.uint8]

_LIVE_PREFIXES = ("rtsp://", "rtmp://", "http://", "https://", "udp://", "tcp://")


class DecodeError(RuntimeError):
    """A source could not be opened, or a non-live source failed mid-decode."""


class FrozenFrameDetector:
    """spec 8.1: a stream can stall without disconnecting. Byte-identical
    consecutive frames for longer than `after_seconds` mean the source is
    frozen and should be treated as offline, not as a static scene."""

    def __init__(self, after_seconds: float = 30.0) -> None:
        self.after_seconds = after_seconds
        self._prev: Frame | None = None
        self._since: float | None = None

    def check(self, frame: Frame, now: float) -> bool:
        """True once the stream has been frozen past the threshold."""
        if (
            self._prev is not None
            and self._prev.shape == frame.shape
            and np.array_equal(self._prev, frame)
        ):
            if self._since is None:
                self._since = now
            return now - self._since >= self.after_seconds
        self._prev = frame
        self._since = None
        return False


def is_live_source(source: str) -> bool:
    """A webcam index or a network stream. These are expected to drop and recover;
    a file is not, so a file decode error is fatal."""
    return source.isdigit() or source.startswith(_LIVE_PREFIXES)


def source_spec(source: str) -> tuple[str, str | None, dict[str, str]]:
    """Return (url, av_format, options). A bare integer means /dev/videoN."""
    if source.isdigit():
        return f"/dev/video{source}", "v4l2", {}
    # `timeout` is the socket I/O timeout in microseconds; without it a dead
    # network source hangs av.open forever (ffmpeg 7 renamed it from `stimeout`).
    if source.startswith("rtsp://"):
        # TCP transport is far more reliable than default UDP over real networks.
        return source, None, {"rtsp_transport": "tcp", "timeout": "10000000"}
    if "://" in source:
        return source, None, {"timeout": "10000000"}
    return source, None, {}


def _open(url: str, fmt: str | None, options: dict[str, str]) -> av.container.InputContainer:
    try:
        return av.open(url, format=fmt, options=options)
    except av.FFmpegError as exc:
        raise DecodeError(f"cannot open source {url!r}: {exc}") from exc


def _decode_once(
    container: av.container.InputContainer, target_fps: float, start_t: float
) -> Iterator[tuple[float, Frame]]:
    """Decode one open container, emitting at roughly target_fps. Timestamps are
    `start_t` plus the container's own elapsed stream time, so a reconnect can
    resume the clock instead of jumping back to zero."""
    stream = container.streams.video[0]
    stream.thread_type = "AUTO"
    interval = 1.0 / target_fps if target_fps > 0 else 0.0
    wall_start = time.monotonic()
    first_pts_t: float | None = None
    last_local = 0.0
    next_emit = 0.0

    for frame in container.decode(stream):
        if frame.pts is not None and stream.time_base is not None:
            raw = float(frame.pts * stream.time_base)
            if first_pts_t is None:
                first_pts_t = raw
            local = raw - first_pts_t
            # Guard against non-monotonic PTS on flaky streams.
            if local < last_local:
                local = last_local
        else:
            local = time.monotonic() - wall_start
        last_local = local

        if local + 1e-6 < next_emit:
            continue
        next_emit = local + interval
        yield start_t + local, cast(Frame, frame.to_ndarray(format="rgb24"))


def decode_frames(
    source: str,
    target_fps: float,
    *,
    max_reconnects: int = 5,
    backoff_base: float = 1.0,
    backoff_cap: float = 30.0,
) -> Iterator[tuple[float, Frame]]:
    """Yield (timestamp_seconds, rgb_uint8_HWC) at roughly target_fps.

    Decoding every frame and dropping most is wasteful, but seeking on a live
    RTSP stream isn't possible, so we decode and skip. Even so this cuts the
    expensive part (inference) by 6-10x versus running it on every frame
    (spec 6.2).

    A live source (RTSP/webcam) that drops or ends is reopened with capped
    exponential backoff, up to `max_reconnects` consecutive failures. A file
    that fails mid-decode raises `DecodeError` instead: that is a real problem,
    not a transient one.
    """
    url, fmt, options = source_spec(source)
    live = is_live_source(source)
    start_t = 0.0
    failures = 0

    while True:
        container = _open(url, fmt, options)
        try:
            for t, frame in _decode_once(container, target_fps, start_t):
                start_t = t  # resume point if the stream drops
                failures = 0
                yield t, frame
        except av.FFmpegError as exc:
            if not live:
                raise DecodeError(f"decode failed for {url!r}: {exc}") from exc
            failures += 1
            if failures > max_reconnects:
                raise DecodeError(
                    f"giving up on {url!r} after {max_reconnects} reconnect attempts: {exc}"
                ) from exc
            time.sleep(min(backoff_cap, backoff_base * 2 ** (failures - 1)))
            continue
        finally:
            container.close()

        if not live:
            return  # clean end of file

        failures += 1
        if failures > max_reconnects:
            raise DecodeError(
                f"live source {url!r} ended and did not recover after {max_reconnects} attempts"
            )
        time.sleep(min(backoff_cap, backoff_base * 2 ** (failures - 1)))
