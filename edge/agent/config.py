from __future__ import annotations

import os
from dataclasses import dataclass

_DEVICES = ("cpu", "cuda")


class ConfigError(ValueError):
    """Raised for an invalid config value, whether from a field or the environment."""


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        raise ConfigError(f"{name}={raw!r} is not a number") from None


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
    # Catchment (spec 6.4): the polygon dilated by this fraction. A track that
    # reaches the catchment but never the zone is a passerby. Normalized-space
    # stand-in for the spec's "2 m equivalent" until ground-plane calibration;
    # tune per camera.
    catchment_frac: float = 0.08
    # Rollup bucket width in stream-time seconds (spec 6.5). 15 minutes is the
    # usual foot-traffic granularity. A run shorter than one bucket produces a
    # single bucket.
    bucket_seconds: float = 900.0
    # Local SQLite buffer for 15-minute rollups until the sync client ships them.
    sqlite_path: str = "./edge_local.db"
    # Cloud endpoint and pairing, used by the sync client.
    cloud_url: str = "https://api.whaletale.tech"
    pairing_token: str = ""

    def __post_init__(self) -> None:
        if self.target_fps <= 0:
            raise ConfigError(f"target_fps must be > 0, got {self.target_fps}")
        if self.device not in _DEVICES:
            raise ConfigError(f"device must be one of {_DEVICES}, got {self.device!r}")
        if not 0.0 < self.score_threshold <= 1.0:
            raise ConfigError(f"score_threshold must be in (0, 1], got {self.score_threshold}")
        if self.min_dwell_seconds < 0:
            raise ConfigError(f"min_dwell_seconds must be >= 0, got {self.min_dwell_seconds}")
        if self.exit_margin_frac < 0:
            raise ConfigError(f"exit_margin_frac must be >= 0, got {self.exit_margin_frac}")
        if self.catchment_frac < 0:
            raise ConfigError(f"catchment_frac must be >= 0, got {self.catchment_frac}")
        if self.bucket_seconds <= 0:
            raise ConfigError(f"bucket_seconds must be > 0, got {self.bucket_seconds}")

    @staticmethod
    def from_env() -> Config:
        return Config(
            target_fps=_env_float("EDGE_TARGET_FPS", 4.0),
            device=os.getenv("EDGE_INFERENCE_DEVICE", "cpu"),
            detector=os.getenv("EDGE_DETECTOR", "rtdetr"),
            model_id=os.getenv("EDGE_MODEL_ID", "PekingU/rtdetr_r50vd"),
            hf_cache=os.getenv("EDGE_HF_CACHE", ".hf_cache"),
            score_threshold=_env_float("EDGE_SCORE_THRESHOLD", 0.5),
            min_dwell_seconds=_env_float("EDGE_MIN_DWELL_SECONDS", 3.0),
            exit_margin_frac=_env_float("EDGE_EXIT_MARGIN_FRAC", 0.02),
            catchment_frac=_env_float("EDGE_CATCHMENT_FRAC", 0.08),
            bucket_seconds=_env_float("EDGE_BUCKET_SECONDS", 900.0),
            sqlite_path=os.getenv("EDGE_SQLITE_PATH", "./edge_local.db"),
            cloud_url=os.getenv("WHALETALE_CLOUD_URL", "https://api.whaletale.tech"),
            pairing_token=os.getenv("WHALETALE_PAIRING_TOKEN", ""),
        )
