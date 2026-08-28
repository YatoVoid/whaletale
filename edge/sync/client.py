"""Watermark sync client (spec M4, 8.4).

The watermark is the set of rows with `synced_at IS NULL`. `push_once` ships a
batch, and only marks them synced on a 2xx ack, so a dropped WAN just means the
same rows go again next time. The cloud upserts on `(zone_version_id,
bucket_start)` / `(site_id, bucket_start)`, so a resend is harmless.

No third-party HTTP dependency: `urllib.request`, wrapped so tests can inject a
fake transport.
"""

from __future__ import annotations

import json
import shutil
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from agent import __version__
from agent.store import SCHEMA_VERSION, BucketStore

# (url, json_payload, bearer_token) -> (status_code, body_bytes)
Poster = Callable[[str, dict[str, Any], str], tuple[int, bytes]]

_OBS_KEYS = (
    "zone_version_id",
    "bucket_start",
    "bucket_end",
    "entries",
    "exits",
    "peak_occupancy",
    "occupied_seconds",
    "dwell_p50_seconds",
    "dwell_p90_seconds",
    "passersby",
    "capture_events",
)
_SITE_KEYS = ("site_id", "bucket_start", "bucket_end", "total_people", "active_cameras")


@dataclass
class PushResult:
    ok: bool
    observations_sent: int = 0
    site_totals_sent: int = 0
    status: int | None = None
    error: str | None = None


@dataclass
class HeartbeatResult:
    ok: bool
    status: int | None = None
    error: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


def _default_poster(url: str, payload: dict[str, Any], token: str) -> tuple[int, bytes]:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:  # 4xx/5xx
        return exc.code, exc.read()


class SyncClient:
    def __init__(
        self,
        store: BucketStore,
        cloud_url: str,
        site_id: str,
        pairing_token: str,
        *,
        poster: Poster | None = None,
        started_at: float | None = None,
    ) -> None:
        self.store = store
        self.base = cloud_url.rstrip("/")
        self.site_id = site_id
        self.token = pairing_token
        self._post: Poster = poster or _default_poster
        self._started = started_at if started_at is not None else time.monotonic()
        self.last_sync_at: str | None = None

    def push_once(self, batch: int = 500) -> PushResult:
        obs = self.store.unsynced_observations(batch)
        totals = self.store.unsynced_site_totals(batch)
        if not obs and not totals:
            return PushResult(ok=True)

        payload = {
            "schema_version": SCHEMA_VERSION,
            "site_id": self.site_id,
            "observations": [_pick(r, _OBS_KEYS) for r in obs],
            "site_totals": [_pick(r, _SITE_KEYS) for r in totals],
        }
        try:
            status, _body = self._post(f"{self.base}/v1/ingest", payload, self.token)
        except (urllib.error.URLError, OSError) as exc:  # offline (spec 8.4)
            return PushResult(ok=False, error=str(exc))

        if not 200 <= status < 300:
            return PushResult(ok=False, status=status, error=f"HTTP {status}")

        when = datetime.now(UTC)
        self.store.mark_observations_synced(
            [(r["zone_version_id"], r["bucket_start"]) for r in obs], when
        )
        self.store.mark_site_totals_synced(
            [(r["site_id"], r["bucket_start"]) for r in totals], when
        )
        self.last_sync_at = when.isoformat()
        return PushResult(
            ok=True,
            observations_sent=len(obs),
            site_totals_sent=len(totals),
            status=status,
        )

    def drain(self, batch: int = 500, max_rounds: int = 100) -> PushResult:
        """Keep pushing batches until nothing is left or a push fails."""
        total_obs = total_site = 0
        for _ in range(max_rounds):
            r = self.push_once(batch)
            if not r.ok:
                return r
            total_obs += r.observations_sent
            total_site += r.site_totals_sent
            if r.observations_sent == 0 and r.site_totals_sent == 0:
                break
        return PushResult(ok=True, observations_sent=total_obs, site_totals_sent=total_site)

    def heartbeat_payload(self, per_camera: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        try:
            _total, _used, free = shutil.disk_usage(".")
            disk_free = int(free)
        except OSError:
            disk_free = -1
        return {
            "site_id": self.site_id,
            "agent_version": __version__,
            "schema_version": SCHEMA_VERSION,
            "uptime_seconds": round(time.monotonic() - self._started, 1),
            "disk_free_bytes": disk_free,
            "buckets_pending_sync": self.store.pending_count(),
            "last_sync_at": self.last_sync_at,
            "per_camera": per_camera or [],
        }

    def heartbeat(self, per_camera: list[dict[str, Any]] | None = None) -> HeartbeatResult:
        payload = self.heartbeat_payload(per_camera)
        try:
            status, _body = self._post(f"{self.base}/v1/heartbeat", payload, self.token)
        except (urllib.error.URLError, OSError) as exc:
            return HeartbeatResult(ok=False, error=str(exc), payload=payload)
        ok = 200 <= status < 300
        return HeartbeatResult(
            ok=ok, status=status, error=None if ok else f"HTTP {status}", payload=payload
        )


def _pick(row: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {k: row[k] for k in keys}
