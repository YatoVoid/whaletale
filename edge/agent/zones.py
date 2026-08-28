from __future__ import annotations

from shapely.geometry import Point, Polygon

# M1: one hand-coded zone. Points are normalized [x, y] in 0..1 (spec rule 5.2.4:
# never pixels, so a camera resolution change can't silently invalidate a zone).
# This default covers the lower-centre of a typical wide camera shot; adjust to
# match your test clip. The live overlay editor arrives in M6.
DEFAULT_ZONE_POLYGON: list[tuple[float, float]] = [
    (0.30, 0.55),
    (0.70, 0.55),
    (0.78, 0.95),
    (0.22, 0.95),
]


def ground_point(bbox_norm: tuple[float, float, float, float]) -> tuple[float, float]:
    """Bottom-centre of a normalized (x1, y1, x2, y2) box.

    Spec 6.4: never the box centre. A tall person at the frame edge would be
    attributed to the wrong zone.
    """
    x1, _y1, x2, y2 = bbox_norm
    return ((x1 + x2) / 2.0, y2)


class Zone:
    """A named polygon with three containment tests:

    - ``contains_enter``: inside the polygon itself (spec 6.4, entry).
    - ``contains_stay``: inside the polygon dilated by ``exit_margin`` (spec 8.2
      hysteresis, so a track loitering on the boundary doesn't flicker).
    - ``contains_catchment``: inside the polygon dilated by ``catchment_margin``
      (spec 6.4 passerby: a track that reaches the catchment but never the zone).

    All buffering is in normalized space, a mild approximation (x and y aren't
    the same pixel scale) that is good enough until ground-plane calibration.
    """

    def __init__(
        self,
        name: str,
        polygon: list[tuple[float, float]],
        exit_margin: float = 0.02,
        catchment_margin: float = 0.08,
    ) -> None:
        if len(polygon) < 3:
            raise ValueError(f"zone {name!r} needs >= 3 points, got {len(polygon)}")
        if exit_margin < 0 or catchment_margin < 0:
            raise ValueError(f"zone {name!r} margins must be >= 0")
        self.name = name
        self._poly = Polygon(polygon)
        if not self._poly.is_valid:
            raise ValueError(f"zone {name!r} polygon is self-intersecting")
        self._stay_poly = self._poly.buffer(exit_margin)
        self._catchment_poly = self._poly.buffer(catchment_margin)

    def contains_enter(self, gp: tuple[float, float]) -> bool:
        return bool(self._poly.covers(Point(gp)))

    def contains_stay(self, gp: tuple[float, float]) -> bool:
        return bool(self._stay_poly.covers(Point(gp)))

    def contains_catchment(self, gp: tuple[float, float]) -> bool:
        return bool(self._catchment_poly.covers(Point(gp)))


class ExclusionMask:
    """spec 8.2: an area the operator marks as staff-only (behind a counter, a
    corridor). A detection whose ground point falls inside is dropped before any
    counting zone sees it, so repeated staff crossings stop inflating entries.
    A small buffer keeps a foot on the boundary line excluded."""

    def __init__(self, polygon: list[tuple[float, float]], *, margin: float = 0.01) -> None:
        if len(polygon) < 3:
            raise ValueError(f"exclusion mask needs >= 3 points, got {len(polygon)}")
        poly = Polygon(polygon)
        if not poly.is_valid:
            raise ValueError("exclusion mask polygon is self-intersecting")
        self._poly = poly.buffer(margin) if margin else poly

    def contains(self, gp: tuple[float, float]) -> bool:
        return bool(self._poly.covers(Point(gp)))


def default_zone(exit_margin: float = 0.02, catchment_margin: float = 0.08) -> Zone:
    return Zone(
        "zone-1",
        DEFAULT_ZONE_POLYGON,
        exit_margin=exit_margin,
        catchment_margin=catchment_margin,
    )


def parse_zone(
    spec: str | None,
    exit_margin: float = 0.02,
    catchment_margin: float = 0.08,
) -> Zone:
    """Build a zone from a CLI spec.

    - ``None`` -> the hand-coded default polygon
    - ``"full"`` -> the whole frame (useful to sanity-check detection + counting)
    - ``"x1,y1,x2,y2"`` -> an axis-aligned rectangle, normalized 0..1
    """
    if spec is None:
        return default_zone(exit_margin, catchment_margin)
    if spec == "full":
        return Zone(
            "full-frame",
            [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)],
            exit_margin=exit_margin,
            catchment_margin=catchment_margin,
        )
    try:
        parts = [float(v) for v in spec.split(",")]
    except ValueError:
        raise ValueError("zone rectangle must be 'x1,y1,x2,y2' with numeric values") from None
    if len(parts) != 4:
        raise ValueError("zone rectangle must be 'x1,y1,x2,y2'")
    x1, y1, x2, y2 = parts
    if not all(0.0 <= v <= 1.0 for v in parts):
        raise ValueError("zone rectangle coordinates must be normalized to 0..1")
    if x1 >= x2 or y1 >= y2:
        raise ValueError("zone rectangle needs x1 < x2 and y1 < y2")
    return Zone(
        "rect",
        [(x1, y1), (x2, y1), (x2, y2), (x1, y2)],
        exit_margin=exit_margin,
        catchment_margin=catchment_margin,
    )
