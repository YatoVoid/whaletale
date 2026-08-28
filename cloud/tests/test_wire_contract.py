"""The ingest payload the edge builds must parse as `schemas.wire.IngestRequest`.

The edge `BucketStore.unsynced_observations()` returns rows with exactly these
column names (see `edge/agent/store.py`); `sync/client.py` drops `synced_at` and
posts the rest. This test pins that shape so a schema change on either side
fails here.
"""

from __future__ import annotations

from schemas.wire import HeartbeatRequest, IngestRequest, ObservationIn, SiteTotalIn

# Mirrors edge/agent/store.py column order, minus `synced_at`.
_EDGE_OBS_ROW = {
    "zone_version_id": "zv-1",
    "bucket_start": "2026-06-01T12:00:00+00:00",
    "bucket_end": "2026-06-01T12:15:00+00:00",
    "entries": 12,
    "exits": 11,
    "peak_occupancy": 3,
    "occupied_seconds": 540.0,
    "dwell_p50_seconds": 42.0,
    "dwell_p90_seconds": 110.0,
    "passersby": 7,
    "capture_events": 12,
}
_EDGE_SITE_ROW = {
    "site_id": "site-1",
    "bucket_start": "2026-06-01T12:00:00+00:00",
    "total_people": 210,
    "active_cameras": 2,
}


def test_edge_observation_row_parses() -> None:
    ObservationIn.model_validate(_EDGE_OBS_ROW)


def test_edge_site_total_row_parses() -> None:
    SiteTotalIn.model_validate(_EDGE_SITE_ROW)


def test_full_ingest_payload_round_trips() -> None:
    req = IngestRequest.model_validate(
        {
            "schema_version": 1,
            "site_id": "site-1",
            "observations": [_EDGE_OBS_ROW],
            "site_totals": [_EDGE_SITE_ROW],
        }
    )
    assert req.observations[0].entries == 12
    # what the cloud would receive over the wire again
    assert "synced_at" not in req.model_dump(mode="json")["observations"][0]


def test_edge_heartbeat_payload_parses() -> None:
    # Mirrors edge/sync/client.py heartbeat_payload().
    hb = HeartbeatRequest.model_validate(
        {
            "schema_version": 1,
            "site_id": "site-1",
            "agent_version": "0.4.0",
            "uptime_seconds": 1234.5,
            "disk_free_bytes": 9_000_000_000,
            "buckets_pending_sync": 3,
            "last_sync_at": None,
            "per_camera": [
                {"id": "cam-a", "status": "online", "fps_actual": 3.9, "mean_confidence": 0.71}
            ],
        }
    )
    assert hb.per_camera[0].id == "cam-a"
