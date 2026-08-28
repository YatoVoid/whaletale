"""Fleet health from heartbeats (spec 9).

`evaluate_fleet` derives, per site, the state of every paired box and the alert
conditions the spec names:
  - a camera dark > `camera_dark_hours` (1h)
  - sync stale > `sync_stale_hours` (6h)
  - disk free < `disk_low_fraction` (20%)
  - a camera's mean confidence down > `confidence_drop` (30%) from its baseline
  - the agent version behind `current_agent_version`

`sync_alerts` upserts one open `alerts` row per (site, kind, subject) and
resolves rows whose condition has cleared. Delivery (Sentry, email, webhook) is
a thin layer on top; the spec says use Sentry for exceptions and not to build
error tracking.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from whaletale_cloud import __version__
from whaletale_cloud import models as m


@dataclass(frozen=True)
class Alert:
    kind: str
    severity: str  # "warning" | "critical"
    audience: str  # "us" | "customer"
    subject: str
    message: str
    site_id: UUID
    edge_box_id: UUID | None = None


@dataclass
class BoxHealth:
    box_id: UUID
    name: str | None
    agent_version: str | None
    last_seen_at: datetime | None
    disk_free_fraction: float | None
    buckets_pending_sync: int | None
    online: bool


@dataclass
class SiteHealth:
    site_id: UUID
    site_name: str
    boxes: list[BoxHealth] = field(default_factory=list)
    alerts: list[Alert] = field(default_factory=list)

    @property
    def state(self) -> str:
        if any(a.severity == "critical" for a in self.alerts):
            return "critical"
        if self.alerts:
            return "warning"
        return "ok"


@dataclass(frozen=True)
class FleetConfig:
    camera_dark_hours: float = 1.0
    sync_stale_hours: float = 6.0
    disk_low_fraction: float = 0.20
    confidence_drop: float = 0.30
    current_agent_version: str = __version__
    baseline_heartbeats: int = 20


def evaluate_fleet(
    session: Session, *, now: datetime | None = None, config: FleetConfig | None = None
) -> list[SiteHealth]:
    now = now or datetime.now(UTC)
    cfg = config or FleetConfig()

    sites = {s.id: s for s in session.scalars(select(m.Site))}
    out: list[SiteHealth] = []
    for site in sites.values():
        sh = SiteHealth(site_id=site.id, site_name=site.name)
        boxes = list(
            session.scalars(
                select(m.EdgeBox).where(
                    m.EdgeBox.site_id == site.id, m.EdgeBox.revoked_at.is_(None)
                )
            )
        )
        for box in boxes:
            latest = session.scalar(
                select(m.Heartbeat)
                .where(m.Heartbeat.edge_box_id == box.id)
                .order_by(m.Heartbeat.received_at.desc())
                .limit(1)
            )
            sh.boxes.append(_box_health(box, latest, now))
            sh.alerts.extend(_box_alerts(session, site, box, latest, now, cfg))
        out.append(sh)
    return out


def _box_health(box: m.EdgeBox, hb: m.Heartbeat | None, now: datetime) -> BoxHealth:
    frac: float | None = None
    if hb and hb.disk_total_bytes:
        frac = hb.disk_free_bytes / hb.disk_total_bytes
    return BoxHealth(
        box_id=box.id,
        name=box.name,
        agent_version=box.agent_version,
        last_seen_at=box.last_seen_at,
        disk_free_fraction=frac,
        buckets_pending_sync=hb.buckets_pending_sync if hb else None,
        online=box.last_seen_at is not None and (now - box.last_seen_at) < timedelta(hours=1),
    )


def _box_alerts(
    session: Session,
    site: m.Site,
    box: m.EdgeBox,
    hb: m.Heartbeat | None,
    now: datetime,
    cfg: FleetConfig,
) -> list[Alert]:
    alerts: list[Alert] = []
    box_label = box.name or str(box.id)[:8]

    # agent version behind
    if box.agent_version and box.agent_version != cfg.current_agent_version:
        alerts.append(
            Alert(
                kind="agent_behind",
                severity="warning",
                audience="us",
                subject=box_label,
                message=(
                    f"{box_label} runs agent v{box.agent_version}; "
                    f"current is v{cfg.current_agent_version}."
                ),
                site_id=site.id,
                edge_box_id=box.id,
            )
        )

    if hb is None:
        alerts.append(
            Alert(
                kind="never_reported",
                severity="warning",
                audience="us",
                subject=box_label,
                message=f"{box_label} has never sent a heartbeat since pairing.",
                site_id=site.id,
                edge_box_id=box.id,
            )
        )
        return alerts

    # sync stale
    last_sync = hb.last_sync_at or box.last_seen_at
    if last_sync and (now - last_sync) > timedelta(hours=cfg.sync_stale_hours):
        hours = (now - last_sync).total_seconds() / 3600
        alerts.append(
            Alert(
                kind="sync_stale",
                severity="critical" if hours > 24 else "warning",
                audience="us",
                subject=box_label,
                message=f"{box_label} last synced {hours:.0f}h ago.",
                site_id=site.id,
                edge_box_id=box.id,
            )
        )

    # disk low
    if hb.disk_total_bytes:
        frac = hb.disk_free_bytes / hb.disk_total_bytes
        if frac < cfg.disk_low_fraction:
            alerts.append(
                Alert(
                    kind="disk_low",
                    severity="critical" if frac < 0.1 else "warning",
                    audience="us",
                    subject=box_label,
                    message=f"{box_label} disk is {frac * 100:.0f}% free.",
                    site_id=site.id,
                    edge_box_id=box.id,
                )
            )

    # per-camera: dark, and confidence drop
    baseline = _confidence_baseline(session, box.id, cfg.baseline_heartbeats)
    for cam in hb.per_camera:
        name = str(cam.get("id", "camera"))
        last_frame = _parse_dt(cam.get("last_frame_at"))
        if last_frame is None or (now - last_frame) > timedelta(hours=cfg.camera_dark_hours):
            since = last_frame.isoformat(timespec="minutes") if last_frame else "an unknown time"
            alerts.append(
                Alert(
                    kind="camera_dark",
                    severity="critical",
                    audience="customer",
                    subject=name,
                    message=(
                        f"Camera {name} has been offline since {since}. "
                        "Check that it has power and a network connection."
                    ),
                    site_id=site.id,
                    edge_box_id=box.id,
                )
            )
            continue
        mc = cam.get("mean_confidence")
        base = baseline.get(name)
        if isinstance(mc, int | float) and base and mc < base * (1 - cfg.confidence_drop):
            alerts.append(
                Alert(
                    kind="low_confidence",
                    severity="warning",
                    audience="us",
                    subject=name,
                    message=(
                        f"Camera {name} detection confidence {mc:.2f} is well below "
                        f"its baseline {base:.2f} (night mode, sun, or a moved camera)."
                    ),
                    site_id=site.id,
                    edge_box_id=box.id,
                )
            )
    return alerts


def _confidence_baseline(session: Session, box_id: UUID, n: int) -> dict[str, float]:
    rows = session.scalars(
        select(m.Heartbeat.per_camera)
        .where(m.Heartbeat.edge_box_id == box_id)
        .order_by(m.Heartbeat.received_at.desc())
        .limit(n)
    )
    samples: dict[str, list[float]] = {}
    for per_camera in rows:
        for cam in per_camera:
            mc = cam.get("mean_confidence")
            if isinstance(mc, int | float):
                samples.setdefault(str(cam.get("id", "camera")), []).append(float(mc))
    return {k: statistics.fmean(v) for k, v in samples.items() if len(v) >= 3}


def sync_alerts(
    session: Session, evaluated: list[SiteHealth], *, now: datetime | None = None
) -> int:
    """Upsert open alert rows to match `evaluated`; resolve those that cleared.
    Returns the number of newly opened alerts."""
    now = now or datetime.now(UTC)
    open_rows = {
        (r.site_id, r.kind, r.subject): r
        for r in session.scalars(select(m.Alert).where(m.Alert.resolved_at.is_(None)))
    }
    current: set[tuple[UUID, str, str]] = set()
    opened = 0
    for sh in evaluated:
        for a in sh.alerts:
            key = (a.site_id, a.kind, a.subject)
            current.add(key)
            if key not in open_rows:
                session.add(
                    m.Alert(
                        site_id=a.site_id,
                        edge_box_id=a.edge_box_id,
                        kind=a.kind,
                        severity=a.severity,
                        audience=a.audience,
                        subject=a.subject,
                        message=a.message,
                        opened_at=now,
                    )
                )
                opened += 1
            else:
                open_rows[key].message = a.message
                open_rows[key].severity = a.severity
    for key, row in open_rows.items():
        if key not in current:
            row.resolved_at = now
    return opened


def _parse_dt(v: object) -> datetime | None:
    if not isinstance(v, str):
        return None
    try:
        dt = datetime.fromisoformat(v)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
