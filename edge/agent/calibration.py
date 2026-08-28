"""Camera-drift detection (spec 8.1).

A fixed camera that gets bumped or re-aimed keeps producing frames, but the
zones now cover the wrong floor and every count after that is quietly wrong.
This compares a cheap perceptual hash of the live view against a reference
captured at calibration time; a sustained divergence flags the camera for
recalibration and the pipeline stops counting it (a visible gap beats wrong
data).

The reference hash lives on the box only. No frame, crop, or hash is ever
synced (spec 6.3).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np

from agent.detect import Frame

_HASH_W = 9
_HASH_H = 8  # dHash compares horizontally-adjacent columns -> 8x8 = 64 bits


def dhash(frame: Frame) -> int:
    """64-bit difference hash. Greyscale, shrink to 9x8 by nearest sampling,
    then one bit per (pixel brighter than its left neighbour)."""
    gray = frame.astype(np.float64).mean(axis=2)
    h, w = gray.shape
    ys = np.linspace(0, h - 1, _HASH_H).astype(np.intp)
    xs = np.linspace(0, w - 1, _HASH_W).astype(np.intp)
    small = gray[np.ix_(ys, xs)]
    diff = small[:, 1:] > small[:, :-1]
    bits = 0
    for b in diff.flatten():
        bits = (bits << 1) | int(b)
    return bits


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def _safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", name) or "camera"


class RefStore:
    """Per-camera reference hashes under one directory, one JSON file each."""

    def __init__(self, directory: str | Path) -> None:
        self.dir = Path(directory)

    def _path(self, camera_name: str) -> Path:
        return self.dir / f"{_safe_name(camera_name)}.json"

    def get(self, camera_name: str) -> int | None:
        p = self._path(camera_name)
        if not p.exists():
            return None
        try:
            return int(json.loads(p.read_text())["dhash"])
        except (ValueError, KeyError, OSError):
            return None

    def set(self, camera_name: str, value: int) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self._path(camera_name).write_text(json.dumps({"dhash": value}))


class DriftDetector:
    """Feeds are perceptual hashes of recent frames. Reports drift once the
    hash has stayed more than `threshold` bits from the reference for
    `samples_needed` consecutive checks."""

    def __init__(
        self, reference: int | None, *, threshold: int = 12, samples_needed: int = 2
    ) -> None:
        self.reference = reference
        self.threshold = threshold
        self.samples_needed = samples_needed
        self._streak = 0

    def feed(self, current: int) -> bool:
        if self.reference is None:
            return False
        if hamming(current, self.reference) > self.threshold:
            self._streak += 1
        else:
            self._streak = 0
        return self._streak >= self.samples_needed
