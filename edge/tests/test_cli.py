from __future__ import annotations

import pytest

from agent.cli import main


def test_missing_source_without_warm_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 2
    assert "--source is required" in capsys.readouterr().err


def test_bad_fps_exits_2_before_loading_a_model(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--source", "x.mp4", "--fps", "-1"]) == 2
    assert "--fps must be > 0" in capsys.readouterr().err


def test_negative_seconds_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--source", "x.mp4", "--seconds", "-5"]) == 2
    assert "--seconds" in capsys.readouterr().err


def test_bad_zone_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--source", "x.mp4", "--zone", "0.9,0.1,0.2,0.4"]) == 2
    assert "--zone" in capsys.readouterr().err


def test_bad_env_exits_2(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EDGE_TARGET_FPS", "quick")
    assert main(["--warm"]) == 2
    assert "EDGE_TARGET_FPS" in capsys.readouterr().err
