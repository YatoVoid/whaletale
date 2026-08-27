from __future__ import annotations

import pytest

from agent.config import Config, ConfigError


def test_defaults() -> None:
    c = Config()
    assert c.target_fps == 4.0
    assert c.min_dwell_seconds == 3.0
    assert c.device == "cpu"


def test_from_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDGE_TARGET_FPS", "7")
    monkeypatch.setenv("EDGE_INFERENCE_DEVICE", "cuda")
    monkeypatch.setenv("EDGE_MODEL_ID", "custom/model")
    monkeypatch.setenv("EDGE_SCORE_THRESHOLD", "0.3")
    monkeypatch.setenv("EDGE_MIN_DWELL_SECONDS", "5")
    monkeypatch.setenv("EDGE_EXIT_MARGIN_FRAC", "0.05")
    c = Config.from_env()
    assert c.target_fps == 7.0
    assert c.device == "cuda"
    assert c.model_id == "custom/model"
    assert c.score_threshold == 0.3
    assert c.min_dwell_seconds == 5.0
    assert c.exit_margin_frac == 0.05


def test_from_env_defaults_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in (
        "EDGE_TARGET_FPS",
        "EDGE_INFERENCE_DEVICE",
        "EDGE_MODEL_ID",
        "EDGE_HF_CACHE",
        "EDGE_SCORE_THRESHOLD",
        "EDGE_MIN_DWELL_SECONDS",
        "EDGE_EXIT_MARGIN_FRAC",
    ):
        monkeypatch.delenv(k, raising=False)
    c = Config.from_env()
    assert c.target_fps == 4.0
    assert c.model_id == "PekingU/rtdetr_r50vd"
    assert c.score_threshold == 0.5


def test_non_numeric_env_value_names_the_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDGE_TARGET_FPS", "fast")
    with pytest.raises(ConfigError, match="EDGE_TARGET_FPS"):
        Config.from_env()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"target_fps": 0},
        {"target_fps": -1},
        {"device": "gpu"},
        {"score_threshold": 0},
        {"score_threshold": 1.5},
        {"min_dwell_seconds": -0.1},
        {"exit_margin_frac": -1},
    ],
)
def test_invalid_field_values_rejected(kwargs: dict[str, object]) -> None:
    with pytest.raises(ConfigError):
        Config(**kwargs)  # type: ignore[arg-type]
