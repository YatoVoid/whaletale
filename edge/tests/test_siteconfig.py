from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.siteconfig import SiteConfigError, load_site_config, parse_site_config

_EXAMPLE = Path(__file__).resolve().parents[1] / "site.example.json"


def _valid() -> dict[str, object]:
    data: dict[str, object] = json.loads(_EXAMPLE.read_text())
    return data


def test_example_config_parses() -> None:
    cfg = parse_site_config(_valid())
    assert cfg.site_id
    assert len(cfg.cameras) == 2
    assert cfg.zone_count == 4  # 3 counting + 1 excluded
    counting = [z for c in cfg.cameras for z in c.zones if not z.excluded]
    assert len(counting) == 3
    assert cfg.cameras[1].zones[0].zone_version_id.startswith("2222")


def test_load_from_file(tmp_path: Path) -> None:
    p = tmp_path / "site.json"
    p.write_text(_EXAMPLE.read_text())
    assert load_site_config(p).zone_count == 4


def test_missing_file_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(SiteConfigError, match="not found"):
        load_site_config(tmp_path / "nope.json")


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda c: c.pop("site_id"), "site_id"),
        (lambda c: c.pop("pairing_token"), "pairing_token"),
        (lambda c: c.update(cameras=[]), "non-empty list"),
        (lambda c: c["cameras"][0].pop("source"), "name.*source"),
        (
            lambda c: c["cameras"][0]["zones"][0].update(polygon=[[0.1, 0.1], [0.9, 0.9]]),
            ">= 3 points",
        ),
        (
            lambda c: c["cameras"][0]["zones"][0].update(
                polygon=[[0.1, 0.1], [1.4, 0.2], [0.3, 0.9]]
            ),
            "0..1",
        ),
        (
            lambda c: c["cameras"][1]["zones"].append(c["cameras"][1]["zones"][0]),
            "duplicate zone_version_id",
        ),
    ],
)
def test_invalid_configs_are_rejected(mutate: object, match: str) -> None:
    cfg = _valid()
    mutate(cfg)  # type: ignore[operator]
    with pytest.raises(SiteConfigError, match=match):
        parse_site_config(cfg)


def test_build_zone_from_zone_config() -> None:
    zc = parse_site_config(_valid()).cameras[0].zones[0]
    zone = zc.build_zone(exit_margin=0.02, catchment_margin=0.08)
    assert zone.contains_enter((0.5, 0.8))


def test_excluded_zone_parses_and_is_marked() -> None:
    cfg = _valid()
    cfg["cameras"][0]["zones"].append(  # type: ignore[index]
        {
            "zone_version_id": "excl-1",
            "polygon": [[0.0, 0.0], [0.2, 0.0], [0.2, 0.3], [0.0, 0.3]],
            "excluded": True,
        }
    )
    parsed = parse_site_config(cfg)
    excl = {z.zone_version_id for c in parsed.cameras for z in c.zones if z.excluded}
    assert "excl-1" in excl
    assert parsed.cameras[0].zones[0].excluded is False


def test_a_config_with_only_excluded_zones_is_rejected() -> None:
    cfg = _valid()
    for cam in cfg["cameras"]:  # type: ignore[attr-defined]
        for z in cam["zones"]:
            z["excluded"] = True
    with pytest.raises(SiteConfigError, match="no counting zones"):
        parse_site_config(cfg)
