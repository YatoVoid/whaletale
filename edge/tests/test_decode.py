from __future__ import annotations

from agent.decode import source_spec


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


def test_file_path_passes_through() -> None:
    url, fmt, options = source_spec("/data/clip.mp4")
    assert url == "/data/clip.mp4"
    assert fmt is None
    assert options == {}
