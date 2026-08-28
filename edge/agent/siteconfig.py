"""The edge box's local site configuration.

A JSON file (never committed - it carries RTSP credentials and the pairing
token) describing the paired site, its cameras, and the zone polygons with the
cloud-assigned `zone_version_id` for each. M7's onboarding wizard writes this;
until then it is hand-authored from `site.example.json`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from agent.zones import Zone


class SiteConfigError(ValueError):
    pass


@dataclass(frozen=True)
class ZoneConfig:
    zone_version_id: str
    polygon: list[tuple[float, float]]
    kind: str = "stall"  # spec 5.1 space kind; informational on the edge

    def build_zone(self, *, exit_margin: float, catchment_margin: float) -> Zone:
        return Zone(
            self.zone_version_id,
            self.polygon,
            exit_margin=exit_margin,
            catchment_margin=catchment_margin,
        )


@dataclass(frozen=True)
class CameraConfig:
    name: str
    source: str
    zones: list[ZoneConfig] = field(default_factory=list)


@dataclass(frozen=True)
class SiteConfig:
    site_id: str
    cloud_url: str
    pairing_token: str
    cameras: list[CameraConfig] = field(default_factory=list)

    @property
    def zone_count(self) -> int:
        return sum(len(c.zones) for c in self.cameras)


def load_site_config(path: str | Path) -> SiteConfig:
    p = Path(path)
    if not p.is_file():
        raise SiteConfigError(f"site config not found: {p}")
    try:
        raw = json.loads(p.read_text())
    except json.JSONDecodeError as exc:
        raise SiteConfigError(f"{p}: invalid JSON: {exc}") from exc
    return parse_site_config(raw)


def parse_site_config(raw: object) -> SiteConfig:
    if not isinstance(raw, dict):
        raise SiteConfigError("top level must be an object")
    for key in ("site_id", "cloud_url", "pairing_token"):
        if not raw.get(key):
            raise SiteConfigError(f"missing {key!r}")

    cameras_raw = raw.get("cameras")
    if not isinstance(cameras_raw, list) or not cameras_raw:
        raise SiteConfigError("'cameras' must be a non-empty list")

    seen_zone_ids: set[str] = set()
    cameras: list[CameraConfig] = []
    for i, cam in enumerate(cameras_raw):
        if not isinstance(cam, dict) or not cam.get("name") or not cam.get("source"):
            raise SiteConfigError(f"cameras[{i}] needs 'name' and 'source'")
        zones_raw = cam.get("zones") or []
        if not isinstance(zones_raw, list):
            raise SiteConfigError(f"cameras[{i}].zones must be a list")
        zones: list[ZoneConfig] = []
        for j, z in enumerate(zones_raw):
            where = f"cameras[{i}].zones[{j}]"
            if not isinstance(z, dict) or not z.get("zone_version_id"):
                raise SiteConfigError(f"{where} needs 'zone_version_id'")
            zid = str(z["zone_version_id"])
            if zid in seen_zone_ids:
                raise SiteConfigError(f"{where}: duplicate zone_version_id {zid!r}")
            seen_zone_ids.add(zid)
            polygon = _parse_polygon(z.get("polygon"), where)
            # Reuse Zone's geometry validation (>= 3 points, 0..1, non-self-intersecting).
            try:
                Zone(zid, polygon)
            except ValueError as exc:
                raise SiteConfigError(f"{where}: {exc}") from exc
            zones.append(ZoneConfig(zid, polygon, str(z.get("kind", "stall"))))
        cameras.append(CameraConfig(str(cam["name"]), str(cam["source"]), zones))

    if not seen_zone_ids:
        raise SiteConfigError("no zones defined on any camera")

    return SiteConfig(
        site_id=str(raw["site_id"]),
        cloud_url=str(raw["cloud_url"]),
        pairing_token=str(raw["pairing_token"]),
        cameras=cameras,
    )


def _parse_polygon(raw: object, where: str) -> list[tuple[float, float]]:
    if not isinstance(raw, list):
        raise SiteConfigError(f"{where}.polygon must be a list of [x, y] pairs")
    points: list[tuple[float, float]] = []
    for pt in raw:
        if not isinstance(pt, list | tuple) or len(pt) != 2:
            raise SiteConfigError(f"{where}.polygon has a non-pair vertex")
        x, y = float(pt[0]), float(pt[1])
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            raise SiteConfigError(f"{where}.polygon vertex ({x}, {y}) is not normalized to 0..1")
        points.append((x, y))
    return points
