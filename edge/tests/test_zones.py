from __future__ import annotations

import pytest

from agent.zones import Zone, default_zone, ground_point, parse_zone


def test_ground_point_is_bottom_centre() -> None:
    # Spec 6.4: bottom-centre, never the box centre.
    gx, gy = ground_point((0.2, 0.1, 0.4, 0.9))
    assert gx == pytest.approx(0.3)
    assert gy == pytest.approx(0.9)


def test_zone_rejects_fewer_than_three_points() -> None:
    # Spec 8.3: zone drawn with < 3 points -> reject.
    with pytest.raises(ValueError):
        Zone("bad", [(0.0, 0.0), (1.0, 1.0)])


def test_zone_rejects_self_intersecting_polygon() -> None:
    # Spec 8.3: self-intersecting polygon -> refuse to save.
    bowtie = [(0.0, 0.0), (1.0, 1.0), (1.0, 0.0), (0.0, 1.0)]
    with pytest.raises(ValueError):
        Zone("bowtie", bowtie)


def test_contains_enter_and_stay() -> None:
    z = Zone("sq", [(0.4, 0.4), (0.6, 0.4), (0.6, 0.6), (0.4, 0.6)], exit_margin=0.05)
    assert z.contains_enter((0.5, 0.5))
    assert not z.contains_enter((0.5, 0.62))  # just outside
    # Hysteresis: the stay test still holds a little past the edge.
    assert z.contains_stay((0.5, 0.62))
    assert not z.contains_stay((0.5, 0.7))


def test_catchment_is_wider_than_stay_which_is_wider_than_enter() -> None:
    z = Zone(
        "sq",
        [(0.4, 0.4), (0.6, 0.4), (0.6, 0.6), (0.4, 0.6)],
        exit_margin=0.03,
        catchment_margin=0.12,
    )
    inside, band, catchment, far = (0.5, 0.5), (0.5, 0.62), (0.5, 0.70), (0.5, 0.9)
    assert z.contains_enter(inside)
    assert not z.contains_enter(band)
    assert z.contains_stay(band)
    assert not z.contains_stay(catchment)
    assert z.contains_catchment(catchment)
    assert not z.contains_catchment(far)


def test_zone_rejects_negative_margins() -> None:
    with pytest.raises(ValueError):
        Zone("n", [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)], catchment_margin=-0.1)


def test_default_zone_is_valid() -> None:
    z = default_zone()
    assert z.name == "zone-1"
    assert z.contains_enter((0.5, 0.8))


def test_parse_zone_variants() -> None:
    assert parse_zone(None).name == "zone-1"

    full = parse_zone("full")
    assert full.contains_enter((0.01, 0.99))
    assert full.contains_enter((0.5, 0.5))

    rect = parse_zone("0.1,0.2,0.3,0.4")
    assert rect.contains_enter((0.2, 0.3))
    assert not rect.contains_enter((0.5, 0.5))

    with pytest.raises(ValueError):
        parse_zone("0.1,0.2,0.3")


@pytest.mark.parametrize(
    "spec",
    [
        "0.1,0.2,1.4,0.4",  # x2 out of 0..1
        "-0.1,0.2,0.3,0.4",  # x1 out of 0..1
        "0.4,0.2,0.2,0.4",  # x1 >= x2
        "0.1,0.5,0.3,0.5",  # y1 >= y2
        "a,b,c,d",  # non-numeric
    ],
)
def test_parse_zone_rejects_bad_rectangles(spec: str) -> None:
    with pytest.raises(ValueError):
        parse_zone(spec)
