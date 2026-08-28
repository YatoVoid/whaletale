"""Synthetic data for a single demo site (spec M2: "seed with synthetic data").

Deterministic given `rng_seed`. Produces enough shape to exercise every path in
attribution, metrics, and normalization:

  - a reshaped zone (two versions, one boundary) -> version resolution
  - a non-primary failover version on a second camera (spec 6.6)
  - permanent, recurring (RRULE), and one_off tenancies (spec 8.3)
  - a space with a tenancy gap -> a real vacant period
  - a space and two common areas with no tenancy at all
  - a festival Saturday (event annotation, kept in baseline) and a closure day
    (closure annotation, excluded)

Times are authored in the site timezone then stored UTC (spec 5.2.5).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import insert
from sqlalchemy.orm import Session

from schemas.enums import CameraStatus, DayAnnotationKind, SpaceKind, TenancyKind
from whaletale_cloud import models as m

SITE_TZ = "America/Chicago"
OPEN_HOUR = 8
CLOSE_HOUR = 20
BUCKET = timedelta(minutes=15)

# Per space kind: (entries per bucket at the daily peak, dwell p50 seconds, capture rate).
_KIND_PROFILE: dict[SpaceKind, tuple[float, float, float]] = {
    SpaceKind.ENTRANCE: (34.0, 6.0, 0.92),
    SpaceKind.CORRIDOR: (22.0, 9.0, 0.28),
    SpaceKind.STALL: (7.0, 45.0, 0.46),
    SpaceKind.TABLE: (3.0, 780.0, 0.63),
    SpaceKind.PATIO: (5.0, 540.0, 0.55),
}

_LAYOUT: list[tuple[str, SpaceKind]] = [
    ("stall-1", SpaceKind.STALL),
    ("stall-2", SpaceKind.STALL),
    ("stall-3", SpaceKind.STALL),
    ("stall-4", SpaceKind.STALL),
    ("stall-5", SpaceKind.STALL),
    ("stall-6", SpaceKind.STALL),
    ("table-1", SpaceKind.TABLE),
    ("table-2", SpaceKind.TABLE),
    ("patio-1", SpaceKind.PATIO),
    ("corridor-1", SpaceKind.CORRIDOR),
    ("entrance-1", SpaceKind.ENTRANCE),
]


@dataclass
class SeedResult:
    site_id: UUID
    epoch: date  # first day with observations, site-local
    weeks: int
    space_ids: dict[str, UUID] = field(default_factory=dict)
    occupant_ids: dict[str, UUID] = field(default_factory=dict)
    primary_zone_version_ids: dict[str, UUID] = field(default_factory=dict)
    reshaped_space: str = "stall-3"
    reshape_on: date | None = None
    reshape_at_utc: datetime | None = None
    reshape_v1_zone_version_id: UUID | None = None
    failover_space: str = "patio-1"
    vacant_gap_space: str = "stall-4"
    vacant_gap: tuple[date, date] | None = None
    never_leased_space: str = "stall-6"
    festival_day: date | None = None
    closure_day: date | None = None


def seed_demo(
    session: Session,
    *,
    weeks: int = 5,
    start: date | None = None,
    rng_seed: int = 20260601,
) -> SeedResult:
    tz = ZoneInfo(SITE_TZ)
    rng = random.Random(rng_seed)
    epoch = start or date(2026, 6, 1)  # a Monday
    res = SeedResult(site_id=uuid4(), epoch=epoch, weeks=weeks)
    res.reshape_on = epoch + timedelta(weeks=3)
    res.reshape_at_utc = _local_midnight_utc(res.reshape_on, tz)
    res.festival_day = _weekday_on_or_after(epoch + timedelta(weeks=3), 5)  # Saturday, week 4
    res.closure_day = _weekday_on_or_after(epoch + timedelta(weeks=1), 1)  # Tuesday, week 2
    res.vacant_gap = (epoch + timedelta(days=24), epoch + timedelta(days=34))

    site = m.Site(
        id=res.site_id,
        name="Cedar Street Market",
        address="1200 Cedar St",
        timezone=SITE_TZ,
        created_at=datetime.now(UTC),
    )
    cams = [
        m.Camera(
            id=uuid4(),
            site_id=site.id,
            name=f"cam-{c}",
            resolution="1920x1080",
            fps_target=4.0,
            status=CameraStatus.ONLINE,
        )
        for c in ("a", "b", "c")
    ]
    session.add(site)
    session.flush()  # no ORM relationships between these tables, so flush in FK order
    session.add_all(cams)
    session.flush()

    spaces = {
        name: m.Space(id=uuid4(), site_id=site.id, name=name.replace("-", " ").title(), kind=kind)
        for name, kind in _LAYOUT
    }
    for name, sp in spaces.items():
        res.space_ids[name] = sp.id
    session.add_all(spaces.values())
    session.flush()

    epoch_utc = _local_midnight_utc(epoch, tz)
    zone_versions: list[m.ZoneVersion] = []
    for i, (name, _kind) in enumerate(_LAYOUT):
        cam = cams[i % 2]
        if name == res.reshaped_space:
            zv1 = _zone_version(
                spaces[name], cam, _triangle(rng), epoch_utc, res.reshape_at_utc, primary=True
            )
            zv2 = _zone_version(
                spaces[name], cam, _triangle(rng), res.reshape_at_utc, None, primary=True
            )
            zone_versions += [zv1, zv2]
            res.reshape_v1_zone_version_id = zv1.id
            res.primary_zone_version_ids[name] = zv2.id
        else:
            zv = _zone_version(spaces[name], cam, _triangle(rng), epoch_utc, None, primary=True)
            zone_versions.append(zv)
            res.primary_zone_version_ids[name] = zv.id
        if name == res.failover_space:
            zone_versions.append(
                _zone_version(spaces[name], cams[2], _triangle(rng), epoch_utc, None, primary=False)
            )
    session.add_all(zone_versions)
    session.flush()

    occ_names = [
        "Rosa's Tamales",
        "Blue Ridge Coffee",
        "Handbound Books",
        "The Pickle Cart",
        "Vetiver & Ash",
        "Nguyen Ceramics",
        "Foothill Cheese",
        "Marisol Flowers",
        "Third Coast Records",
    ]
    occupants = {n: m.Occupant(id=uuid4(), site_id=site.id, name=n) for n in occ_names}
    for n, o in occupants.items():
        res.occupant_ids[n] = o.id
    session.add_all(occupants.values())
    session.flush()

    gap_start, gap_end = res.vacant_gap
    session.add_all(
        [
            _permanent(spaces["stall-1"], occupants["Rosa's Tamales"], epoch),
            _permanent(spaces["stall-2"], occupants["Nguyen Ceramics"], epoch),
            _recurring(
                spaces["stall-3"],
                occupants["The Pickle Cart"],
                epoch,
                "FREQ=WEEKLY;BYDAY=SA",
                time(8, 0),
                time(14, 0),
            ),
            _permanent(spaces["stall-4"], occupants["Handbound Books"], epoch, ends=gap_start),
            _permanent(spaces["stall-4"], occupants["Vetiver & Ash"], gap_end),
            _one_off(spaces["stall-5"], occupants["Marisol Flowers"], epoch + timedelta(days=12)),
            _permanent(spaces["table-1"], occupants["Blue Ridge Coffee"], epoch),
            _recurring(
                spaces["table-2"],
                occupants["Foothill Cheese"],
                epoch,
                "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR",
                time(11, 0),
                time(15, 0),
            ),
            _permanent(spaces["patio-1"], occupants["Third Coast Records"], epoch),
        ]
    )
    session.add_all(
        [
            m.DayAnnotation(
                id=uuid4(),
                site_id=site.id,
                day=res.festival_day,
                kind=DayAnnotationKind.EVENT,
                label="Cedar Street Fall Festival",
                exclude_from_baseline=False,
                created_by="seed",
            ),
            m.DayAnnotation(
                id=uuid4(),
                site_id=site.id,
                day=res.closure_day,
                kind=DayAnnotationKind.CLOSURE,
                label="Power outage, market closed",
                exclude_from_baseline=True,
                created_by="seed",
            ),
        ]
    )
    session.flush()

    _seed_observations(session, res, spaces, tz)
    session.flush()
    return res


def _seed_observations(
    session: Session, res: SeedResult, spaces: dict[str, m.Space], tz: ZoneInfo
) -> None:
    rng = random.Random(res.weeks * 7919 + 13)
    kinds = dict(_LAYOUT)
    obs_rows: list[dict[str, object]] = []
    total_by_bucket: dict[datetime, int] = {}
    end = res.epoch + timedelta(weeks=res.weeks)

    day = res.epoch
    while day < end:
        weekend = day.weekday() >= 5
        if day == res.closure_day:
            day += timedelta(days=1)
            continue
        festival = day == res.festival_day
        for hour in range(OPEN_HOUR, CLOSE_HOUR):
            for minute in (0, 15, 30, 45):
                bstart = datetime.combine(day, time(hour, minute), tzinfo=tz).astimezone(UTC)
                curve = _hourly_curve(hour + minute / 60.0)
                if curve == 0.0:
                    continue
                for name, kind in kinds.items():
                    zv_id = _effective_zone_version(res, name, bstart)
                    if zv_id is None:
                        continue
                    peak, dwell_p50, capture = _KIND_PROFILE[kind]
                    mult = 1.0
                    if weekend:
                        mult *= 1.6 if kind in (SpaceKind.STALL, SpaceKind.PATIO) else 1.2
                    if festival:
                        mult *= 3.0
                    entries = _poisson(rng, peak * curve * mult)
                    if entries == 0 and rng.random() < 0.6:
                        continue
                    passersby = _poisson(rng, entries * (1.0 - capture) / max(capture, 0.05))
                    dwell50 = max(1.0, rng.gauss(dwell_p50, dwell_p50 * 0.2))
                    dwell90 = dwell50 * rng.uniform(2.0, 3.2)
                    occ_frac = min(1.0, (entries * dwell50) / 900.0)
                    obs_rows.append(
                        {
                            "id": uuid4(),
                            "zone_version_id": zv_id,
                            "bucket_start": bstart,
                            "bucket_end": bstart + BUCKET,
                            "entries": entries,
                            "exits": max(0, entries + rng.randint(-1, 1)),
                            "peak_occupancy": max(1, round(entries * occ_frac)) if entries else 0,
                            "occupied_seconds": round(900.0 * occ_frac, 1),
                            "dwell_p50_seconds": round(dwell50, 1),
                            "dwell_p90_seconds": round(dwell90, 1),
                            "passersby": passersby,
                            "capture_events": entries,
                        }
                    )
                    total_by_bucket[bstart] = total_by_bucket.get(bstart, 0) + entries
        day += timedelta(days=1)

    if obs_rows:
        session.execute(insert(m.Observation), obs_rows)
    site_total_rows = [
        {
            "id": uuid4(),
            "site_id": res.site_id,
            "bucket_start": bstart,
            "total_people": round(n * 1.35) + rng.randint(0, 4),  # + uncounted walk-by
            "active_cameras": 3,
        }
        for bstart, n in sorted(total_by_bucket.items())
    ]
    if site_total_rows:
        session.execute(insert(m.SiteTotal), site_total_rows)


def _effective_zone_version(res: SeedResult, space: str, when: datetime) -> UUID | None:
    if space != res.reshaped_space:
        return res.primary_zone_version_ids[space]
    assert res.reshape_at_utc is not None
    if when >= res.reshape_at_utc:
        return res.primary_zone_version_ids[space]
    return res.reshape_v1_zone_version_id


def _hourly_curve(hour: float) -> float:
    """Midday and late-afternoon retail curve, 0 outside open hours."""
    if hour < OPEN_HOUR or hour >= CLOSE_HOUR:
        return 0.0
    return max(0.12, 0.9 * _bump(hour, 12.5, 1.6) + 1.0 * _bump(hour, 16.5, 2.2))


def _bump(x: float, centre: float, width: float) -> float:
    z = (x - centre) / width
    return math.exp(-z * z)


def _local_midnight_utc(d: date, tz: ZoneInfo) -> datetime:
    return datetime.combine(d, time(0), tzinfo=tz).astimezone(UTC)


def _weekday_on_or_after(d: date, weekday: int) -> date:
    return d + timedelta(days=(weekday - d.weekday()) % 7)


def _zone_version(
    space: m.Space,
    cam: m.Camera,
    polygon: list[list[float]],
    effective_from: datetime,
    effective_to: datetime | None,
    *,
    primary: bool,
) -> m.ZoneVersion:
    return m.ZoneVersion(
        id=uuid4(),
        space_id=space.id,
        camera_id=cam.id,
        polygon=polygon,
        is_primary=primary,
        effective_from=effective_from,
        effective_to=effective_to,
        created_by="seed",
    )


def _triangle(rng: random.Random) -> list[list[float]]:
    cx, cy = rng.uniform(0.3, 0.7), rng.uniform(0.45, 0.8)
    r = rng.uniform(0.08, 0.15)
    return [
        [round(cx, 3), round(cy - r, 3)],
        [round(cx + r, 3), round(cy + r, 3)],
        [round(cx - r, 3), round(cy + r, 3)],
    ]


def _permanent(
    space: m.Space, occ: m.Occupant, starts: date, *, ends: date | None = None
) -> m.Tenancy:
    return m.Tenancy(
        id=uuid4(),
        space_id=space.id,
        occupant_id=occ.id,
        kind=TenancyKind.PERMANENT,
        starts_on=starts,
        ends_on=ends,
        created_at=datetime.now(UTC),
    )


def _recurring(
    space: m.Space, occ: m.Occupant, starts: date, rrule: str, day_start: time, day_end: time
) -> m.Tenancy:
    return m.Tenancy(
        id=uuid4(),
        space_id=space.id,
        occupant_id=occ.id,
        kind=TenancyKind.RECURRING,
        starts_on=starts,
        recurrence_rule=rrule,
        daily_start_time=day_start,
        daily_end_time=day_end,
        created_at=datetime.now(UTC),
    )


def _one_off(space: m.Space, occ: m.Occupant, on: date) -> m.Tenancy:
    return m.Tenancy(
        id=uuid4(),
        space_id=space.id,
        occupant_id=occ.id,
        kind=TenancyKind.ONE_OFF,
        starts_on=on,
        ends_on=on,
        created_at=datetime.now(UTC),
    )


def _poisson(rng: random.Random, lam: float) -> int:
    if lam <= 0:
        return 0
    limit = math.exp(-lam)
    k, p = 0, 1.0
    while True:
        k += 1
        p *= rng.random()
        if p <= limit:
            return k - 1
