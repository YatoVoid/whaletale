"""The camera validation gate (spec 7). A camera is not saved until every check
passes. Fail loudly: a camera that produces garbage silently is worse than one
that never connects.

Checks:
  1. stream opens within `open_timeout` seconds
  2. resolution >= `min_width` x `min_height`
  3. achievable decode FPS >= `min_fps`
  4. a test inference completes in < `inference_budget_ms`
  5. at least one frame decoded without error
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol

from agent.decode import DecodeError, _open, decode_frames, source_spec
from agent.detect import BBoxNorm, Frame


class _Detector(Protocol):
    def detect(self, rgb: Frame) -> list[tuple[BBoxNorm, float]]: ...


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str


@dataclass
class ValidationReport:
    checks: list[Check] = field(default_factory=list)
    resolution: tuple[int, int] | None = None
    achievable_fps: float | None = None
    inference_ms: float | None = None

    @property
    def ok(self) -> bool:
        return bool(self.checks) and all(c.passed for c in self.checks)

    def add(self, name: str, passed: bool, detail: str) -> None:
        self.checks.append(Check(name, passed, detail))

    def render(self) -> str:
        lines = [f"{'PASS' if c.passed else 'FAIL'}  {c.name}: {c.detail}" for c in self.checks]
        lines.append("")
        lines.append("VALID" if self.ok else "NOT VALID — do not save this camera")
        return "\n".join(lines)


def validate_source(
    source: str,
    detector: _Detector | None = None,
    *,
    open_timeout: float = 10.0,
    min_fps: float = 2.0,
    min_width: int = 640,
    min_height: int = 480,
    inference_budget_ms: float = 200.0,
    sample_seconds: float = 3.0,
) -> ValidationReport:
    report = ValidationReport()

    # 1. opens within the timeout
    url, fmt, options = source_spec(source)
    t0 = time.monotonic()
    try:
        container = _open(url, fmt, options)
    except DecodeError as exc:
        report.add("opens", False, str(exc))
        return report
    open_secs = time.monotonic() - t0
    container.close()
    report.add(
        "opens",
        open_secs <= open_timeout,
        f"{open_secs:.1f}s (limit {open_timeout:.0f}s)",
    )

    # 2 / 3 / 5. decode a short sample
    frames = 0
    first_shape: tuple[int, int, int] | None = None
    first_frame: Frame | None = None
    decode_start = time.monotonic()
    try:
        for _t, frame in decode_frames(source, target_fps=10.0, max_reconnects=0):
            if first_shape is None:
                first_shape = frame.shape  # type: ignore[assignment]
                first_frame = frame
            frames += 1
            if time.monotonic() - decode_start >= sample_seconds:
                break
    except DecodeError as exc:
        report.add("decodes a clean frame", frames > 0, str(exc))

    if first_shape is None:
        report.add("decodes a clean frame", False, "no frame decoded")
        report.add("resolution", False, "unknown")
        report.add("achievable fps", False, "0.0")
        return report

    h, w = first_shape[0], first_shape[1]
    report.resolution = (w, h)
    report.add("decodes a clean frame", True, f"{frames} frames in the sample")
    report.add(
        "resolution",
        w >= min_width and h >= min_height,
        f"{w}x{h} (min {min_width}x{min_height})",
    )

    elapsed = max(time.monotonic() - decode_start, 1e-6)
    fps = frames / elapsed
    report.achievable_fps = round(fps, 2)
    report.add("achievable fps", fps >= min_fps, f"{fps:.1f} (min {min_fps:.1f})")

    # 4. test inference latency
    if detector is not None and first_frame is not None:
        detector.detect(first_frame)  # warm any lazy state
        t = time.monotonic()
        detector.detect(first_frame)
        ms = (time.monotonic() - t) * 1000.0
        report.inference_ms = round(ms, 1)
        report.add(
            "test inference",
            ms < inference_budget_ms,
            f"{ms:.0f}ms (budget {inference_budget_ms:.0f}ms)",
        )
    else:
        report.add("test inference", False, "no detector provided")

    return report
