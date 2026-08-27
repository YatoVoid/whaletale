"""Pydantic v2 models mirroring the Section 5.1 data model.

One model per table, representing a persisted row. Cloud SQLAlchemy models map
onto these one-to-one; a test asserts the field sets stay in sync. API request
and response shapes (Create/Update variants) arrive with the API in M5.

Section 5.2 rules that show up here:
  1. observations carry no occupant reference. Attribution is a query-time join.
  4. polygons are normalized 0..1, never pixels.
  5. every datetime is UTC.
"""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field

from schemas.enums import (
    CameraStatus,
    DayAnnotationKind,
    RatePeriod,
    SiteStatus,
    SpaceKind,
    TenancyKind,
)


def _validate_polygon(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if len(points) < 3:
        raise ValueError(f"polygon needs >= 3 points, got {len(points)}")
    for x, y in points:
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            raise ValueError(f"polygon point ({x}, {y}) is outside the normalized 0..1 range")
    return points


# Normalized [x, y] vertices in 0..1 (spec 5.2.4). Self-intersection is rejected
# on save in the cloud with shapely; shared stays dependency-light.
NormalizedPolygon = Annotated[list[tuple[float, float]], AfterValidator(_validate_polygon)]


class _Row(BaseModel):
    """Base for a persisted row: immutable, rejects unknown fields so a schema
    drift between edge and cloud fails loudly instead of silently dropping data."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID


class Site(_Row):
    name: str
    address: str | None = None
    timezone: str = Field(description="IANA name, e.g. 'America/Chicago' (spec 5.2.5)")
    status: SiteStatus = SiteStatus.ACTIVE
    created_at: datetime


class Camera(_Row):
    site_id: UUID
    name: str
    rtsp_url_encrypted: str | None = Field(
        default=None, description="ciphertext only; never plaintext in the cloud (spec 7)"
    )
    resolution: str = Field(pattern=r"^\d+x\d+$", description="e.g. '1920x1080'")
    fps_target: float = Field(gt=0)
    status: CameraStatus = CameraStatus.PENDING
    last_seen_at: datetime | None = None
    credentials_ref: str | None = None


class Space(_Row):
    site_id: UUID
    name: str
    kind: SpaceKind
    parent_space_id: UUID | None = None
    archived_at: datetime | None = None


class ZoneVersion(_Row):
    """Geometry, versioned, never overwritten (spec 5.2.2). A reshape closes the
    current row (`effective_to`) and inserts a new one."""

    space_id: UUID
    camera_id: UUID
    polygon: NormalizedPolygon
    is_primary: bool = Field(description="exactly one primary per space at a time (spec 6.6)")
    effective_from: datetime
    effective_to: datetime | None = None
    created_by: str
    created_at: datetime


class Occupant(_Row):
    site_id: UUID
    name: str
    contact_email: EmailStr | None = None
    contact_phone: str | None = None
    archived_at: datetime | None = None


class Tenancy(_Row):
    """Who occupies a space, when. Never stamped onto an observation (spec 5.2.1)."""

    space_id: UUID
    occupant_id: UUID
    kind: TenancyKind
    starts_on: date
    ends_on: date | None = None
    recurrence_rule: str | None = Field(
        default=None, description="RFC 5545 RRULE, set iff kind == recurring (spec 8.3)"
    )
    daily_start_time: time | None = None
    daily_end_time: time | None = None
    rate_amount: Decimal | None = None
    rate_period: RatePeriod | None = None
    notes: str | None = None
    created_at: datetime


class Observation(_Row):
    """A 15-minute rollup for one zone version. Written by the edge, synced up,
    upserted on (zone_version_id, bucket_start) (spec 8.4). No occupant column."""

    zone_version_id: UUID
    bucket_start: datetime
    bucket_end: datetime
    entries: int = Field(ge=0)
    exits: int = Field(ge=0)
    peak_occupancy: int = Field(ge=0)
    occupied_seconds: float = Field(ge=0)
    dwell_p50_seconds: float = Field(ge=0)
    dwell_p90_seconds: float = Field(ge=0)
    passersby: int = Field(ge=0)
    capture_events: int = Field(
        ge=0, description="entries that count toward capture rate; rate is derived, not stored"
    )


class SiteTotal(_Row):
    """The denominator for traffic share and share-of-site (spec 5.1, 6.4)."""

    site_id: UUID
    bucket_start: datetime
    total_people: int = Field(ge=0)
    active_cameras: int = Field(ge=0)


class DayAnnotation(_Row):
    site_id: UUID
    day: date = Field(description="the annotated calendar date in the site's timezone")
    kind: DayAnnotationKind
    label: str
    exclude_from_baseline: bool = False
    created_by: str
