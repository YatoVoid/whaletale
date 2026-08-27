from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import BaseModel
from sqlalchemy import Engine
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Session

from schemas import models as pyd
from schemas.enums import SpaceKind
from whaletale_cloud import models as orm

# spec 5.1: the nine tables, paired Pydantic <-> ORM.
PAIRS: list[tuple[type[BaseModel], type[DeclarativeBase]]] = [
    (pyd.Site, orm.Site),
    (pyd.Camera, orm.Camera),
    (pyd.Space, orm.Space),
    (pyd.ZoneVersion, orm.ZoneVersion),
    (pyd.Occupant, orm.Occupant),
    (pyd.Tenancy, orm.Tenancy),
    (pyd.Observation, orm.Observation),
    (pyd.SiteTotal, orm.SiteTotal),
    (pyd.DayAnnotation, orm.DayAnnotation),
]


def _orm_columns(model: type[DeclarativeBase]) -> set[str]:
    return {col.key for col in sa_inspect(model).mapper.column_attrs}


@pytest.mark.parametrize(("pyd_model", "orm_model"), PAIRS, ids=lambda m: m.__name__)
def test_pydantic_and_orm_field_sets_match(
    pyd_model: type[BaseModel], orm_model: type[DeclarativeBase]
) -> None:
    pyd_fields = set(pyd_model.model_fields)
    orm_fields = _orm_columns(orm_model)
    assert pyd_fields == orm_fields, (
        f"{pyd_model.__name__}: only in Pydantic {pyd_fields - orm_fields}, "
        f"only in ORM {orm_fields - pyd_fields}"
    )


def test_observations_has_no_occupant_column() -> None:
    # spec 5.2.1: attribution is a query-time join, never stamped on a row.
    assert not any("occupant" in c for c in _orm_columns(orm.Observation))


def test_day_annotation_column_is_named_date() -> None:
    # spec 5.1 calls the column `date`; the attribute is `day` to avoid shadowing.
    assert sa_inspect(orm.DayAnnotation).columns["day"].name == "date"


def test_all_tables_present(engine: Engine) -> None:
    names = set(sa_inspect(engine).get_table_names())
    assert {
        "sites",
        "cameras",
        "spaces",
        "zone_versions",
        "occupants",
        "tenancies",
        "observations",
        "site_totals",
        "day_annotations",
    } <= names


def test_open_primary_zone_version_is_unique_per_space(db: Session) -> None:
    # spec 6.6: exactly one primary zone version open per space at a time.
    site = orm.Site(name="S", timezone="America/Chicago")
    db.add(site)
    db.flush()
    camera = orm.Camera(site_id=site.id, name="C", resolution="1920x1080", fps_target=4.0)
    space = orm.Space(site_id=site.id, name="Stall 1", kind=SpaceKind.STALL)
    db.add_all([camera, space])
    db.flush()

    now = datetime.now(UTC)

    def make_primary() -> orm.ZoneVersion:
        return orm.ZoneVersion(
            space_id=space.id,
            camera_id=camera.id,
            polygon=[[0.1, 0.1], [0.9, 0.1], [0.5, 0.9]],
            is_primary=True,
            effective_from=now,
            created_by="test",
        )

    db.add(make_primary())
    db.flush()
    db.add(make_primary())
    with pytest.raises(IntegrityError):
        db.flush()
