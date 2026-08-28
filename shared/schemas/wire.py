"""The edge <-> cloud sync wire contract (spec 9, M4/M5).

The edge builds these, the cloud parses them. Kept separate from `models.py`
(the persisted row shapes) because a payload version can lag the DB schema -
`schema_version` lets the cloud accept and upgrade an older box's payload
(spec 5.3).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

WIRE_SCHEMA_VERSION = 1


class _Wire(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ObservationIn(_Wire):
    zone_version_id: str
    bucket_start: datetime
    bucket_end: datetime
    entries: int = Field(ge=0)
    exits: int = Field(ge=0)
    peak_occupancy: int = Field(ge=0)
    occupied_seconds: float = Field(ge=0)
    dwell_p50_seconds: float = Field(ge=0)
    dwell_p90_seconds: float = Field(ge=0)
    passersby: int = Field(ge=0)
    capture_events: int = Field(ge=0)


class SiteTotalIn(_Wire):
    site_id: str
    bucket_start: datetime  # spec 5.1: 15-minute bucket, end is implied
    total_people: int = Field(ge=0)
    active_cameras: int = Field(ge=0)


class IngestRequest(_Wire):
    schema_version: int = WIRE_SCHEMA_VERSION
    site_id: str
    observations: list[ObservationIn] = Field(default_factory=list, max_length=5000)
    site_totals: list[SiteTotalIn] = Field(default_factory=list, max_length=5000)


class IngestResponse(_Wire):
    observations_upserted: int
    site_totals_upserted: int


class CameraHealthIn(_Wire):
    """spec 9 per_camera. `id` is the edge-local camera name until onboarding
    (M7) maps it to a cloud camera row."""

    id: str
    status: str
    fps_actual: float | None = None
    mean_confidence: float | None = None
    last_frame_at: datetime | None = None


class HeartbeatRequest(_Wire):
    schema_version: int = WIRE_SCHEMA_VERSION
    site_id: str
    agent_version: str
    uptime_seconds: float = Field(ge=0)
    cpu_percent: float | None = None
    mem_percent: float | None = None
    disk_free_bytes: int
    buckets_pending_sync: int = Field(ge=0)
    last_sync_at: datetime | None = None
    per_camera: list[CameraHealthIn] = Field(default_factory=list)


class HeartbeatResponse(_Wire):
    received_at: datetime
    agent_version_current: str | None = None  # cloud tells the box if it is behind
