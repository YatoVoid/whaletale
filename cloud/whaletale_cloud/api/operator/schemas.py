"""Operator-console API response and request shapes (cloud-only, not on the
edge wire)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from schemas.enums import RatePeriod, TenancyKind


class SiteOut(BaseModel):
    id: UUID
    name: str
    timezone: str
    status: str


class SpaceOut(BaseModel):
    id: UUID
    name: str
    kind: str
    parent_space_id: UUID | None
    archived: bool
    current_occupant: str | None
    current_occupant_id: UUID | None


class OccupantOut(BaseModel):
    id: UUID
    name: str
    contact_email: str | None
    contact_phone: str | None
    archived: bool
    space_names: list[str]


class SpaceMetricsOut(BaseModel):
    period_start: date
    period_end: date
    entries: int
    traffic_share: float | None
    capture_rate: float
    median_dwell_seconds: float
    peer_rank: int | None
    peer_count: int | None
    entries_is_anomaly: bool
    degraded_bucket_count: int


class OccupancySpanOut(BaseModel):
    occupant_name: str | None
    start: date
    end: date


class SpaceDetailOut(BaseModel):
    space: SpaceOut
    metrics: SpaceMetricsOut
    occupancy: list[OccupancySpanOut]


class ScheduleCellOut(BaseModel):
    space_id: UUID
    day: date
    occupant_name: str | None  # None == vacant, shown as a state not a blank (spec 10.3)


class ScheduleGridOut(BaseModel):
    site_id: UUID
    days: list[date]
    space_ids: list[UUID]
    space_names: dict[str, str]
    cells: list[ScheduleCellOut]


class OverviewSpaceRow(BaseModel):
    space_id: UUID
    name: str
    kind: str
    entries: int
    capture_rate: float
    occupant_name: str | None
    is_vacant: bool


class OverviewOut(BaseModel):
    site: SiteOut
    period_start: date
    period_end: date
    spaces: list[OverviewSpaceRow]  # ranked by capture rate
    vacant_space_ids: list[UUID]
    boxes_online: int
    boxes_total: int
    cameras_offline: list[str]


class TenancyIn(BaseModel):
    occupant_id: UUID
    kind: TenancyKind
    starts_on: date
    ends_on: date | None = None
    recurrence_rule: str | None = None
    daily_start_time: str | None = None  # "HH:MM"
    daily_end_time: str | None = None
    rate_amount: Decimal | None = None
    rate_period: RatePeriod | None = None
    notes: str | None = None


class TenancyOut(BaseModel):
    id: UUID
    space_id: UUID
    occupant_id: UUID
    occupant_name: str
    kind: str
    starts_on: date
    ends_on: date | None
    recurrence_rule: str | None


class TenancyConflict(BaseModel):
    detail: str
    conflicting_tenancy_ids: list[UUID]


class OccupantIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    contact_email: str | None = None
    contact_phone: str | None = None


class ReshapeIn(BaseModel):
    polygon: list[tuple[float, float]]
    created_by: str
    # spec 8.4: optimistic lock. The id of the open primary the editor loaded.
    # If another operator has since reshaped, this no longer matches and the
    # save is refused with a conflict instead of silently stacking versions.
    base_version_id: UUID | None = None


class CurrentZoneOut(BaseModel):
    zone_version_id: UUID
    polygon: list[tuple[float, float]]
    version_number: int


class ReshapeOut(BaseModel):
    zone_version_id: UUID
    version_number: int
    previous_version_id: UUID | None
    message: str


class CameraOut(BaseModel):
    id: UUID
    name: str
    resolution: str
    fps_target: float
    status: str
    last_seen_at: datetime | None


class CameraIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    resolution: str = Field(pattern=r"^\d+x\d+$")
    fps_target: float = Field(gt=0)
    rtsp_url_encrypted: str | None = None
    credentials_ref: str | None = None


class EdgeBoxOut(BaseModel):
    id: UUID
    name: str | None
    agent_version: str | None
    last_seen_at: datetime | None
    created_at: datetime


class PairEdgeBoxIn(BaseModel):
    name: str | None = Field(default=None, max_length=200)


class PairEdgeBoxOut(BaseModel):
    id: UUID
    pairing_token: str  # returned once, never stored in plaintext
