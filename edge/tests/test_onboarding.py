from __future__ import annotations

import time
from pathlib import Path

import av
import numpy as np
import pytest

from agent.detect import BBoxNorm, Frame
from onboarding import discovery
from onboarding.credentials import CredentialError, seal, unseal
from onboarding.validation import validate_source

SECRET = "site-secret-under-test"


# --- credentials -------------------------------------------------------


def test_seal_unseal_round_trip() -> None:
    token = seal("admin:hunter2", site_secret=SECRET)
    assert token != "admin:hunter2"
    assert unseal(token, site_secret=SECRET) == "admin:hunter2"


def test_wrong_secret_cannot_decrypt() -> None:
    token = seal("admin:hunter2", site_secret=SECRET)
    with pytest.raises(CredentialError):
        unseal(token, site_secret="a-different-secret")


def test_no_secret_is_an_error() -> None:
    with pytest.raises(CredentialError):
        seal("x", site_secret="")


# --- discovery scope parsing ----------------------------------------


@pytest.mark.parametrize(
    ("scopes", "key", "expected"),
    [
        (("onvif://www.onvif.org/name/Acme_Optics",), "name", "Acme Optics"),
        (("onvif://www.onvif.org/hardware/NVT-4000",), "hardware", "NVT-4000"),
        (("onvif://www.onvif.org/location/lobby",), "name", None),
    ],
)
def test_scope_value(scopes: tuple[str, ...], key: str, expected: str | None) -> None:
    assert discovery._scope_value(scopes, key) == expected


def test_discover_builds_cameras_from_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Svc:
        def getXAddrs(self) -> list[str]:
            return ["http://192.168.1.50/onvif/device_service"]

        def getScopes(self) -> list[str]:
            return [
                "onvif://www.onvif.org/name/Acme",
                "onvif://www.onvif.org/hardware/Cam9",
            ]

    class _WSD:
        def start(self) -> None: ...
        def stop(self) -> None: ...
        def searchServices(self, **_kw: object) -> list[_Svc]:
            return [_Svc(), _Svc()]  # same IP twice -> deduped

    monkeypatch.setattr(discovery, "ThreadedWSDiscovery", _WSD, raising=False)
    import sys
    import types

    fake = types.ModuleType("wsdiscovery")
    fake.QName = lambda *a, **k: object()  # type: ignore[attr-defined]
    disc_mod = types.ModuleType("wsdiscovery.discovery")
    disc_mod.ThreadedWSDiscovery = _WSD  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "wsdiscovery", fake)
    monkeypatch.setitem(sys.modules, "wsdiscovery.discovery", disc_mod)

    cams = discovery.discover(timeout=1.0)
    assert len(cams) == 1
    assert cams[0].ip == "192.168.1.50"
    assert cams[0].manufacturer == "Acme"
    assert cams[0].model == "Cam9"
    assert cams[0].label == "Acme Cam9"


# --- validation gate ----------------------------------------------


def _clip(path: Path, w: int, h: int, n: int = 90, rate: int = 15) -> None:
    c = av.open(str(path), "w")
    s = c.add_stream("mpeg4", rate=rate)
    s.width, s.height, s.pix_fmt = w, h, "yuv420p"
    for i in range(n):
        arr = np.full((h, w, 3), (i * 4) % 256, dtype=np.uint8)
        for pkt in s.encode(av.VideoFrame.from_ndarray(arr, format="rgb24")):
            c.mux(pkt)
    for pkt in s.encode():
        c.mux(pkt)
    c.close()


class _FastDetector:
    def detect(self, rgb: Frame) -> list[tuple[BBoxNorm, float]]:
        return []


class _SlowDetector:
    def detect(self, rgb: Frame) -> list[tuple[BBoxNorm, float]]:
        time.sleep(0.3)
        return []


def test_missing_source_fails_the_opens_check(tmp_path: Path) -> None:
    report = validate_source(str(tmp_path / "nope.mp4"), _FastDetector())
    assert not report.ok
    assert report.checks[0].name == "opens"
    assert not report.checks[0].passed


def test_good_clip_and_fast_detector_validates(tmp_path: Path) -> None:
    clip = tmp_path / "ok.mp4"
    _clip(clip, 1280, 720)
    report = validate_source(str(clip), _FastDetector(), sample_seconds=1.0)
    assert report.resolution == (1280, 720)
    assert report.ok, report.render()


def test_low_resolution_fails(tmp_path: Path) -> None:
    clip = tmp_path / "small.mp4"
    _clip(clip, 320, 240)
    report = validate_source(str(clip), _FastDetector(), sample_seconds=1.0)
    assert not report.ok
    res = next(c for c in report.checks if c.name == "resolution")
    assert not res.passed


def test_slow_inference_fails_the_budget(tmp_path: Path) -> None:
    clip = tmp_path / "ok.mp4"
    _clip(clip, 1280, 720)
    report = validate_source(str(clip), _SlowDetector(), sample_seconds=1.0)
    infer = next(c for c in report.checks if c.name == "test inference")
    assert not infer.passed
    assert not report.ok


def test_no_detector_fails_the_inference_check(tmp_path: Path) -> None:
    clip = tmp_path / "ok.mp4"
    _clip(clip, 1280, 720)
    report = validate_source(str(clip), None, sample_seconds=1.0)
    infer = next(c for c in report.checks if c.name == "test inference")
    assert not infer.passed
