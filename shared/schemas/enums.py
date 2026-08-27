"""Enumerations referenced by the Section 5.1 data model.

Some value sets are given verbatim in the spec (SpaceKind, TenancyKind,
DayAnnotationKind). The rest are the smallest set the spec's behaviour implies
and are marked INFERRED; revisit against the spec author if they matter to a
downstream decision.
"""

from __future__ import annotations

from enum import StrEnum


class SpaceKind(StrEnum):
    """spec 5.1: spaces.kind."""

    STALL = "stall"
    TABLE = "table"
    PATIO = "patio"
    CORRIDOR = "corridor"
    ENTRANCE = "entrance"


class TenancyKind(StrEnum):
    """spec 5.1: tenancies.kind."""

    PERMANENT = "permanent"
    RECURRING = "recurring"
    ONE_OFF = "one_off"


class DayAnnotationKind(StrEnum):
    """spec 5.1: day_annotations.kind."""

    EVENT = "event"
    WEATHER = "weather"
    CLOSURE = "closure"
    MAINTENANCE = "maintenance"


class SiteStatus(StrEnum):
    """spec 5.1: sites.status. INFERRED value set.

    ACTIVE: collecting and billable. SUSPENDED: billing lapsed, dashboard
    read-only, edge keeps collecting (spec 8.5). ARCHIVED: customer cancelled,
    retained for the export/deletion window (spec 8.5).
    """

    ACTIVE = "active"
    SUSPENDED = "suspended"
    ARCHIVED = "archived"


class CameraStatus(StrEnum):
    """spec 5.1: cameras.status. INFERRED value set, drawn from spec 8.1 and 9.

    PENDING: added, not through the onboarding validation gate (spec 7).
    ONLINE / OFFLINE: last heartbeat view. NEEDS_RECALIBRATION: the camera was
    moved or re-aimed and counting is paused (spec 8.1).
    """

    PENDING = "pending"
    ONLINE = "online"
    OFFLINE = "offline"
    NEEDS_RECALIBRATION = "needs_recalibration"


class RatePeriod(StrEnum):
    """spec 5.1: tenancies.rate_period. INFERRED; spec 17 lists day / month /
    percentage of sales as the open pricing question, week added for markets
    that bill by weekend."""

    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    PERCENT_OF_SALES = "percent_of_sales"


class BucketQuality(StrEnum):
    """Per-bucket data-quality marker (spec 6.6, 8.1). Not a stored column on
    its own; carried on report rows so degraded and low-confidence data reads
    differently from clean data (spec 13)."""

    OK = "ok"
    PARTIAL = "partial"  # a camera was offline for part of the bucket (8.1)
    DEGRADED = "degraded"  # primary zone version unavailable, secondary used (6.6)
    LOW_CONFIDENCE = "low_confidence"  # detector confidence dropped sharply (8.1)
