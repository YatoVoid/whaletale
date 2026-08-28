from __future__ import annotations

import urllib.error
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from agent.store import BucketStore, ObservationRecord, SiteTotalRecord
from sync.client import SyncClient

B0 = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def _seed_store(path: Path, n: int = 3) -> BucketStore:
    s = BucketStore(path)
    for i in range(n):
        start = B0 + timedelta(minutes=15 * i)
        s.write_observation(
            ObservationRecord(
                zone_version_id=f"zv-{i}",
                bucket_start=start,
                bucket_end=start + timedelta(minutes=15),
                entries=10 + i,
                exits=9 + i,
                peak_occupancy=2,
                occupied_seconds=500.0,
                dwell_p50_seconds=40.0,
                dwell_p90_seconds=100.0,
                passersby=5,
                capture_events=10 + i,
            )
        )
    s.write_site_total(SiteTotalRecord("site-1", B0, B0 + timedelta(minutes=15), 200, 2))
    return s


class _Recorder:
    def __init__(self, status: int = 200, exc: Exception | None = None) -> None:
        self.status = status
        self.exc = exc
        self.calls: list[tuple[str, dict[str, Any], str]] = []

    def __call__(self, url: str, payload: dict[str, Any], token: str) -> tuple[int, bytes]:
        self.calls.append((url, payload, token))
        if self.exc is not None:
            raise self.exc
        return self.status, b"{}"


def test_push_sends_pending_and_marks_synced(tmp_path: Path) -> None:
    store = _seed_store(tmp_path / "e.db")
    poster = _Recorder(200)
    client = SyncClient(store, "https://c.test/", "site-1", "tok", poster=poster)

    r = client.push_once()
    assert r.ok and r.observations_sent == 3 and r.site_totals_sent == 1
    url, payload, token = poster.calls[0]
    assert url == "https://c.test/v1/ingest"
    assert token == "tok"
    assert payload["site_id"] == "site-1"
    assert len(payload["observations"]) == 3
    assert "synced_at" not in payload["observations"][0]
    assert store.pending_count() == 0


def test_offline_leaves_rows_for_retry(tmp_path: Path) -> None:
    store = _seed_store(tmp_path / "e.db")
    down = _Recorder(exc=urllib.error.URLError("no route to host"))
    client = SyncClient(store, "https://c.test", "site-1", "tok", poster=down)

    r = client.push_once()
    assert not r.ok
    assert store.pending_count() == 4  # nothing marked

    # WAN comes back
    client._post = _Recorder(200)
    r2 = client.push_once()
    assert r2.ok
    assert store.pending_count() == 0


def test_non_2xx_is_not_acked(tmp_path: Path) -> None:
    store = _seed_store(tmp_path / "e.db")
    client = SyncClient(store, "https://c.test", "site-1", "tok", poster=_Recorder(503))
    r = client.push_once()
    assert not r.ok and r.status == 503
    assert store.pending_count() == 4


def test_nothing_pending_is_a_noop(tmp_path: Path) -> None:
    store = BucketStore(tmp_path / "e.db")
    poster = _Recorder(200)
    client = SyncClient(store, "https://c.test", "site-1", "tok", poster=poster)
    r = client.push_once()
    assert r.ok and r.observations_sent == 0
    assert poster.calls == []


def test_drain_pushes_everything_in_batches(tmp_path: Path) -> None:
    store = _seed_store(tmp_path / "e.db", n=7)
    client = SyncClient(store, "https://c.test", "site-1", "tok", poster=_Recorder(200))
    r = client.drain(batch=3)
    assert r.ok and r.observations_sent == 7
    assert store.pending_count() == 0


def test_heartbeat_payload_shape(tmp_path: Path) -> None:
    store = _seed_store(tmp_path / "e.db")
    poster = _Recorder(200)
    client = SyncClient(store, "https://c.test", "site-1", "tok", poster=poster)

    hb = client.heartbeat(per_camera=[{"name": "cam-a", "fps_actual": 3.8}])
    assert hb.ok
    url, payload, _tok = poster.calls[0]
    assert url == "https://c.test/v1/heartbeat"
    assert payload["site_id"] == "site-1"
    assert payload["schema_version"] == 1
    assert payload["buckets_pending_sync"] == 4
    assert payload["per_camera"][0]["name"] == "cam-a"
    assert payload["disk_free_bytes"] >= 0
