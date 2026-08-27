from __future__ import annotations

import pytest

from agent.config import Config


def test_defaults() -> None:
    c = Config()
    assert c.target_fps == 4.0
    assert c.min_dwell_seconds == 3.0
    assert c.device == "cpu"


def test_from_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDGE_TARGET_FPS", "7")
    monkeypatch.setenv("EDGE_INFERENCE_DEVICE", "cuda")
    monkeypatch.setenv("EDGE_MODEL_ID", "custom/model")
    c = Config.from_env()
    assert c.target_fps == 7.0
    assert c.device == "cuda"
    assert c.model_id == "custom/model"


def test_from_env_defaults_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in ("EDGE_TARGET_FPS", "EDGE_INFERENCE_DEVICE", "EDGE_MODEL_ID", "EDGE_HF_CACHE"):
        monkeypatch.delenv(k, raising=False)
    c = Config.from_env()
    assert c.target_fps == 4.0
    assert c.model_id == "PekingU/rtdetr_r50vd"
