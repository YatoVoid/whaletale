from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    target_fps: float = 4.0
    device: str = "cpu"  # "cpu" | "cuda"
    detector: str = "rtdetr"
    model_id: str = "PekingU/rtdetr_r50vd"
    hf_cache: str = ".hf_cache"
    score_threshold: float = 0.5

    # Entry definition (spec 6.4): person must stay inside >= this long.
    min_dwell_seconds: float = 3.0
    # Hysteresis (spec 8.2): once inside, the person is only considered to have
    # left after their ground point clears the polygon dilated by this fraction
    # of the frame's smaller dimension. Keeps a person loitering on the boundary
    # from flickering entries.
    exit_margin_frac: float = 0.02

    @staticmethod
    def from_env() -> Config:
        return Config(
            target_fps=float(os.getenv("EDGE_TARGET_FPS", "4")),
            device=os.getenv("EDGE_INFERENCE_DEVICE", "cpu"),
            detector=os.getenv("EDGE_DETECTOR", "rtdetr"),
            model_id=os.getenv("EDGE_MODEL_ID", "PekingU/rtdetr_r50vd"),
            hf_cache=os.getenv("EDGE_HF_CACHE", ".hf_cache"),
        )
