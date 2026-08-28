from __future__ import annotations

from pathlib import Path

import numpy as np

from agent.calibration import DriftDetector, RefStore, dhash, hamming


def _stripe(x0: int) -> np.ndarray:
    """A full-height vertical bar - stands in for structure that shifts when a
    camera is re-aimed."""
    a = np.zeros((48, 64, 3), dtype=np.uint8)
    a[:, x0 : x0 + 10] = 220
    return a


def test_dhash_is_stable_and_position_sensitive() -> None:
    a = _stripe(6)
    assert dhash(a) == dhash(a.copy())  # deterministic
    moved = _stripe(42)
    assert hamming(dhash(a), dhash(moved)) > 8  # a re-aimed camera diverges


def test_hamming_counts_differing_bits() -> None:
    assert hamming(0b1011, 0b1011) == 0
    assert hamming(0b1011, 0b0000) == 3


def test_refstore_roundtrip_and_missing(tmp_path: Path) -> None:
    store = RefStore(tmp_path / "refs")
    assert store.get("cam-a") is None
    store.set("cam-a", 123456789)
    assert store.get("cam-a") == 123456789
    assert store.get("cam-b") is None


def test_drift_detector_needs_a_reference() -> None:
    d = DriftDetector(None, threshold=4, samples_needed=1)
    assert d.feed(dhash(_stripe(6))) is False


def test_drift_detector_flags_after_sustained_divergence() -> None:
    ref = dhash(_stripe(6))
    d = DriftDetector(ref, threshold=8, samples_needed=2)
    moved = dhash(_stripe(42))
    assert d.feed(moved) is False  # one bad sample is not enough
    assert d.feed(moved) is True  # two in a row -> drifted


def test_drift_detector_resets_when_the_view_returns() -> None:
    ref = dhash(_stripe(6))
    d = DriftDetector(ref, threshold=8, samples_needed=2)
    moved = dhash(_stripe(42))
    d.feed(moved)
    d.feed(ref)  # back to the reference view; streak resets
    assert d.feed(moved) is False
