from __future__ import annotations

import time
from collections.abc import Iterator
from typing import cast

import av
import numpy as np
import numpy.typing as npt

Frame = npt.NDArray[np.uint8]


def source_spec(source: str) -> tuple[str, str | None, dict[str, str]]:
    """Return (url, av_format, options). A bare integer means /dev/videoN."""
    if source.isdigit():
        return f"/dev/video{source}", "v4l2", {}
    if source.startswith("rtsp://"):
        # TCP transport is far more reliable than default UDP over real networks.
        return source, None, {"rtsp_transport": "tcp", "stimeout": "10000000"}
    return source, None, {}


def decode_frames(source: str, target_fps: float) -> Iterator[tuple[float, Frame]]:
    """Yield (timestamp_seconds, rgb_uint8_HWC) at roughly target_fps.

    Decoding every frame and dropping most is wasteful, but seeking on a live
    RTSP stream isn't possible, so we decode and skip. Even so this cuts the
    expensive part (inference) by 6-10x versus running it on every frame
    (spec 6.2).
    """
    url, fmt, options = source_spec(source)
    container = av.open(url, format=fmt, options=options)
    try:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        interval = 1.0 / target_fps if target_fps > 0 else 0.0
        wall_start = time.monotonic()
        next_emit = 0.0
        last_pts_t: float | None = None

        for frame in container.decode(stream):
            if frame.pts is not None and stream.time_base is not None:
                t = float(frame.pts * stream.time_base)
                # Guard against non-monotonic PTS on flaky streams.
                if last_pts_t is not None and t < last_pts_t:
                    t = last_pts_t
                last_pts_t = t
            else:
                t = time.monotonic() - wall_start

            if t + 1e-6 < next_emit:
                continue
            next_emit = t + interval

            yield t, cast(Frame, frame.to_ndarray(format="rgb24"))
    finally:
        container.close()
