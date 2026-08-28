"""SQLAlchemy 2.0 ORM for the Section 5.1 tables.

Field sets mirror `schemas.models`; `tests/test_schema_parity.py` fails if they
drift. Section 5.2 invariants are enforced here as constraints, not left to
application code:
  - observations have no occupant column (5.2.1)
  - zone_versions is append-only in practice; a partial unique index keeps at
    most one open primary per space (6.6)
  - polygons are JSON arrays, validated 0..1 by the Pydantic layer and by a
    shapely check on save (5.2.4, 8.3)
  - every timestamp column is timezone-aware UTC (5.2.5)
"""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    MetaData,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from schemas.enums import (
    CameraStatus,
    DayAnnotationKind,
    RatePeriod,
    SiteStatus,
    SpaceKind,
    TenancyKind,
)


def _pg_enum(enum_cls: type[StrEnum], name: str) -> Enum:
    """A Postgres enum whose labels are the members' string values (e.g.
    'recurring'), not their Python names. CHECK constraints in the schema
    compare against these values."""
    return Enum(
        enum_cls,
        name=name,
        values_callable=lambda e: [str(m.value) for m in e],
    )


_NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=_NAMING)


def _pk() -> Mapped[UUID]:
    return mapped_column(primary_key=True, default=uuid4)


def _utc(**kw: object) -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), **kw)  # type: ignore[arg-type]


class Site(Base):
    __tablename__ = "sites"

    id: Mapped[UUID] = _pk()
    name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str | None] = mapped_column(String(500))
    timezone: Mapped[str] = mapped_column(String(64))
    status: Mapped[SiteStatus] = mapped_column(
        _pg_enum(SiteStatus, "site_status"), default=SiteStatus.ACTIVE
    )
    created_at: Mapped[datetime] = _utc(server_default=text("now()"))


class Camera(Base):
    __tablename__ = "cameras"

    id: Mapped[UUID] = _pk()
    site_id: Mapped[UUID] = mapped_column(ForeignKey("sites.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(String(200))
    rtsp_url_encrypted: Mapped[str | None] = mapped_column(String)
    resolution: Mapped[str] = mapped_column(String(16))
    fps_target: Mapped[float] = mapped_column()
    status: Mapped[CameraStatus] = mapped_column(
        _pg_enum(CameraStatus, "camera_status"), default=CameraStatus.PENDING
    )
    last_seen_at: Mapped[datetime | None] = _utc()
    credentials_ref: Mapped[str | None] = mapped_column(String(200))

    __table_args__ = (
        CheckConstraint("fps_target > 0", name="fps_target_positive"),
        CheckConstraint("resolution ~ '^[0-9]+x[0-9]+$'", name="resolution_shape"),
    )


class Space(Base):
    __tablename__ = "spaces"

    id: Mapped[UUID] = _pk()
    site_id: Mapped[UUID] = mapped_column(ForeignKey("sites.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[SpaceKind] = mapped_column(_pg_enum(SpaceKind, "space_kind"))
    parent_space_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("spaces.id", ondelete="RESTRICT")
    )
    archived_at: Mapped[datetime | None] = _utc()


class ZoneVersion(Base):
    __tablename__ = "zone_versions"

    id: Mapped[UUID] = _pk()
    space_id: Mapped[UUID] = mapped_column(ForeignKey("spaces.id", ondelete="RESTRICT"))
    camera_id: Mapped[UUID] = mapped_column(ForeignKey("cameras.id", ondelete="RESTRICT"))
    polygon: Mapped[list[list[float]]] = mapped_column(JSONB)
    is_primary: Mapped[bool] = mapped_column()
    effective_from: Mapped[datetime] = _utc()
    effective_to: Mapped[datetime | None] = _utc()
    created_by: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = _utc(server_default=text("now()"))

    __table_args__ = (
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="effective_range_ordered",
        ),
        # spec 6.6: at most one open primary version per space.
        Index(
            "uq_zone_versions_open_primary",
            "space_id",
            unique=True,
            postgresql_where=text("is_primary AND effective_to IS NULL"),
        ),
    )


class Occupant(Base):
    __tablename__ = "occupants"

    id: Mapped[UUID] = _pk()
    site_id: Mapped[UUID] = mapped_column(ForeignKey("sites.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(String(200))
    contact_email: Mapped[str | None] = mapped_column(String(320))
    contact_phone: Mapped[str | None] = mapped_column(String(64))
    archived_at: Mapped[datetime | None] = _utc()


class Tenancy(Base):
    __tablename__ = "tenancies"

    id: Mapped[UUID] = _pk()
    space_id: Mapped[UUID] = mapped_column(ForeignKey("spaces.id", ondelete="RESTRICT"))
    occupant_id: Mapped[UUID] = mapped_column(ForeignKey("occupants.id", ondelete="RESTRICT"))
    kind: Mapped[TenancyKind] = mapped_column(_pg_enum(TenancyKind, "tenancy_kind"))
    starts_on: Mapped[date] = mapped_column()
    ends_on: Mapped[date | None] = mapped_column()
    recurrence_rule: Mapped[str | None] = mapped_column(String(500))
    daily_start_time: Mapped[time | None] = mapped_column()
    daily_end_time: Mapped[time | None] = mapped_column()
    rate_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    rate_period: Mapped[RatePeriod | None] = mapped_column(_pg_enum(RatePeriod, "rate_period"))
    notes: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = _utc(server_default=text("now()"))

    occupant: Mapped[Occupant] = relationship(lazy="joined")

    __table_args__ = (
        CheckConstraint(
            "(kind = 'recurring') = (recurrence_rule IS NOT NULL)",
            name="recurrence_rule_iff_recurring",
        ),
        CheckConstraint(
            "ends_on IS NULL OR ends_on >= starts_on",
            name="tenancy_range_ordered",
        ),
        CheckConstraint(
            "(daily_start_time IS NULL) = (daily_end_time IS NULL)",
            name="daily_window_paired",
        ),
    )


class Observation(Base):
    __tablename__ = "observations"

    id: Mapped[UUID] = _pk()
    zone_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("zone_versions.id", ondelete="RESTRICT")
    )
    bucket_start: Mapped[datetime] = _utc()
    bucket_end: Mapped[datetime] = _utc()
    entries: Mapped[int] = mapped_column()
    exits: Mapped[int] = mapped_column()
    peak_occupancy: Mapped[int] = mapped_column()
    occupied_seconds: Mapped[float] = mapped_column()
    dwell_p50_seconds: Mapped[float] = mapped_column()
    dwell_p90_seconds: Mapped[float] = mapped_column()
    passersby: Mapped[int] = mapped_column()
    capture_events: Mapped[int] = mapped_column()

    __table_args__ = (
        # spec 8.4: duplicate sync payloads upsert on this key.
        UniqueConstraint("zone_version_id", "bucket_start", name="zone_version_bucket"),
        CheckConstraint("bucket_end > bucket_start", name="bucket_range_ordered"),
        CheckConstraint(
            "entries >= 0 AND exits >= 0 AND peak_occupancy >= 0 AND passersby >= 0 "
            "AND capture_events >= 0 AND occupied_seconds >= 0 "
            "AND dwell_p50_seconds >= 0 AND dwell_p90_seconds >= 0",
            name="counts_non_negative",
        ),
        CheckConstraint("capture_events <= entries", name="capture_events_within_entries"),
    )


class SiteTotal(Base):
    __tablename__ = "site_totals"

    id: Mapped[UUID] = _pk()
    site_id: Mapped[UUID] = mapped_column(ForeignKey("sites.id", ondelete="RESTRICT"))
    bucket_start: Mapped[datetime] = _utc()
    total_people: Mapped[int] = mapped_column()
    active_cameras: Mapped[int] = mapped_column()

    __table_args__ = (
        UniqueConstraint("site_id", "bucket_start", name="site_bucket"),
        CheckConstraint("total_people >= 0 AND active_cameras >= 0", name="totals_non_negative"),
    )


class DayAnnotation(Base):
    __tablename__ = "day_annotations"

    id: Mapped[UUID] = _pk()
    site_id: Mapped[UUID] = mapped_column(ForeignKey("sites.id", ondelete="RESTRICT"))
    # `date` in the spec; renamed to avoid shadowing the type. Column name kept.
    day: Mapped[date] = mapped_column("date")
    kind: Mapped[DayAnnotationKind] = mapped_column(
        _pg_enum(DayAnnotationKind, "day_annotation_kind")
    )
    label: Mapped[str] = mapped_column(String(300))
    exclude_from_baseline: Mapped[bool] = mapped_column(default=False)
    created_by: Mapped[str] = mapped_column(String(200))


class EdgeBox(Base):
    """A paired on-prem agent (spec 8.4: a replaced box re-pairs with a token).
    Not in Section 5.1 - added with M5."""

    __tablename__ = "edge_boxes"

    id: Mapped[UUID] = _pk()
    site_id: Mapped[UUID] = mapped_column(ForeignKey("sites.id", ondelete="RESTRICT"))
    name: Mapped[str | None] = mapped_column(String(200))
    token_hash: Mapped[str] = mapped_column(String(64))  # sha256 hex of the bearer token
    agent_version: Mapped[str | None] = mapped_column(String(64))
    last_seen_at: Mapped[datetime | None] = _utc()
    created_at: Mapped[datetime] = _utc(server_default=text("now()"))
    revoked_at: Mapped[datetime | None] = _utc()

    __table_args__ = (UniqueConstraint("token_hash", name="token_hash"),)


class Heartbeat(Base):
    """Fleet telemetry (spec 9). Stored raw; alerting on it is M8."""

    __tablename__ = "heartbeats"

    id: Mapped[UUID] = _pk()
    edge_box_id: Mapped[UUID] = mapped_column(ForeignKey("edge_boxes.id", ondelete="CASCADE"))
    site_id: Mapped[UUID] = mapped_column(ForeignKey("sites.id", ondelete="RESTRICT"))
    received_at: Mapped[datetime] = _utc(server_default=text("now()"))
    agent_version: Mapped[str] = mapped_column(String(64))
    uptime_seconds: Mapped[float] = mapped_column()
    cpu_percent: Mapped[float | None] = mapped_column()
    mem_percent: Mapped[float | None] = mapped_column()
    disk_free_bytes: Mapped[int] = mapped_column(BigInteger)
    disk_total_bytes: Mapped[int | None] = mapped_column(BigInteger)
    buckets_pending_sync: Mapped[int] = mapped_column()
    last_sync_at: Mapped[datetime | None] = _utc()
    per_camera: Mapped[list[dict[str, object]]] = mapped_column(JSONB)


class OperatorUser(Base):
    """A console user. Real login is Auth.js (spec 12); until the frontend wires
    that in, the API trusts a hashed bearer token. `site_ids` scopes every query
    to this user's sites (improve-vibe-code: row-level tenant checks). Added with
    M6."""

    __tablename__ = "operator_users"

    id: Mapped[UUID] = _pk()
    email: Mapped[str] = mapped_column(String(320))
    name: Mapped[str | None] = mapped_column(String(200))
    token_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = _utc(server_default=text("now()"))
    disabled_at: Mapped[datetime | None] = _utc()

    __table_args__ = (
        UniqueConstraint("email"),
        UniqueConstraint("token_hash"),
    )


class OperatorUserSite(Base):
    __tablename__ = "operator_user_sites"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("operator_users.id", ondelete="CASCADE"), primary_key=True
    )
    site_id: Mapped[UUID] = mapped_column(
        ForeignKey("sites.id", ondelete="CASCADE"), primary_key=True
    )


class Alert(Base):
    """A fleet-health condition (spec 9). One open row per (site, box, kind);
    `resolved_at` is set when the condition clears. Added with M8."""

    __tablename__ = "alerts"

    id: Mapped[UUID] = _pk()
    site_id: Mapped[UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"))
    edge_box_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("edge_boxes.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(64))  # camera_dark | sync_stale | disk_low | ...
    severity: Mapped[str] = mapped_column(String(16))  # warning | critical
    audience: Mapped[str] = mapped_column(String(16))  # us | customer
    subject: Mapped[str] = mapped_column(String(200))  # e.g. the camera name
    message: Mapped[str] = mapped_column(String(500))
    opened_at: Mapped[datetime] = _utc(server_default=text("now()"))
    resolved_at: Mapped[datetime | None] = _utc()

    __table_args__ = (
        Index(
            "uq_alerts_open",
            "site_id",
            "kind",
            "subject",
            unique=True,
            postgresql_where=text("resolved_at IS NULL"),
        ),
    )


class Subscription(Base):
    """One Stripe subscription per site, billed on camera count (spec 8.5, 12).
    Camera quantity is derived from `cameras` rows server-side, never trusted
    from the client. Added with M9."""

    __tablename__ = "subscriptions"

    id: Mapped[UUID] = _pk()
    site_id: Mapped[UUID] = mapped_column(ForeignKey("sites.id", ondelete="RESTRICT"))
    stripe_customer_id: Mapped[str] = mapped_column(String(64))
    stripe_subscription_id: Mapped[str] = mapped_column(String(64))
    stripe_price_id: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24))  # active | past_due | canceled | trialing
    camera_quantity: Mapped[int] = mapped_column()
    current_period_end: Mapped[datetime | None] = _utc()
    grace_until: Mapped[datetime | None] = _utc()  # set on payment failure
    canceled_at: Mapped[datetime | None] = _utc()
    export_ready_at: Mapped[datetime | None] = _utc()  # cancel -> export, then delete
    updated_at: Mapped[datetime] = _utc(server_default=text("now()"))

    __table_args__ = (
        UniqueConstraint("site_id", name="one_subscription_per_site"),
        UniqueConstraint("stripe_subscription_id"),
    )
