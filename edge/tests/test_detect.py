"""Integration check for PersonDetector.

RT-DETR weights are ~110 MB and git-ignored, so CI (which syncs a clean tree)
never has them and these tests skip there. Locally, after one real run has
populated EDGE_HF_CACHE, they exercise the detector end to end.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

from agent.decode import Frame

MODEL_ID = "PekingU/rtdetr_r18vd"  # the smaller model, for a faster test
CACHE = Path(os.getenv("EDGE_HF_CACHE", ".hf_cache"))
_CACHED = (CACHE / "models--PekingU--rtdetr_r18vd").is_dir()

pytestmark = pytest.mark.skipif(not _CACHED, reason=f"{MODEL_ID} weights not cached under {CACHE}")


@pytest.fixture(scope="module")
def detector() -> object:
    from agent.detect import PersonDetector

    return PersonDetector(model_id=MODEL_ID, device="cpu", hf_cache=str(CACHE))


def _sample_frame() -> Frame:
    for candidate in (Path(".smoke/people.mp4"), Path("edge/.smoke/people.mp4")):
        if candidate.is_file():
            from agent.decode import decode_frames

            for _t, frame in decode_frames(str(candidate), target_fps=1.0):
                return frame
    return np.zeros((480, 640, 3), dtype=np.uint8)


def test_detect_returns_normalized_boxes(detector: object) -> None:
    dets = detector.detect(_sample_frame())  # type: ignore[attr-defined]
    assert isinstance(dets, list)
    for (x1, y1, x2, y2), score in dets:
        assert 0.0 <= x1 < x2 <= 1.0
        assert 0.0 <= y1 < y2 <= 1.0
        assert 0.5 <= score <= 1.0


def test_blank_frame_has_no_people(detector: object) -> None:
    dets = detector.detect(np.zeros((360, 640, 3), dtype=np.uint8))  # type: ignore[attr-defined]
    assert dets == []
