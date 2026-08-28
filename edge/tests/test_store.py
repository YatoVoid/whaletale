from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from agent.store import (
    BucketStore,
    IntegrityError,
    ObservationRecord,
    SiteTotalRecord,
)

B0 = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def _obs(zv: str = "zv-1", start: datetime = B0, entries: int = 10) -> ObservationRecord:
    return ObservationRecord(
        zone_version_id=zv,
        bucket_start=start,
        bucket_end=start + timedelta(minutes=15),
        entries=entries,
        exits=entries - 1,
        peak_occupancy=3,
        occupied_seconds=540.0,
        dwell_p50_seconds=42.0,
        dwell_p90_seconds=110.0,
        passersby=12,
        capture_events=entries,
    )


def test_write_then_read_unsynced_then_mark(tmp_path: Path) -> None:
    with BucketStore(tmp_path / "edge.db") as s:
        s.write_observation(_obs())
        pending = s.unsynced_observations()
        assert len(pending) == 1
        assert pending[0]["entries"] == 10
        assert pending[0]["synced_at"] is None

        s.mark_observations_synced(
            [(pending[0]["zone_version_id"], pending[0]["bucket_start"])],
            datetime.now(UTC),
        )
        assert s.unsynced_observations() == []
        assert s.pending_count() == 0


def test_upsert_overwrites_and_rearms_for_sync(tmp_path: Path) -> None:
    with BucketStore(tmp_path / "edge.db") as s:
        s.write_observation(_obs(entries=5))
        s.mark_observations_synced([("zv-1", B0.isoformat())], datetime.now(UTC))
        assert s.pending_count() == 0

        s.write_observation(_obs(entries=99))  # same key, re-processed
        rows = s.unsynced_observations()
        assert len(rows) == 1
        assert rows[0]["entries"] == 99
        assert rows[0]["synced_at"] is None


def test_site_totals_round_trip(tmp_path: Path) -> None:
    with BucketStore(tmp_path / "edge.db") as s:
        s.write_site_total(SiteTotalRecord("site-1", B0, 240, 3))
        rows = s.unsynced_site_totals()
        assert rows[0]["total_people"] == 240
        assert s.pending_count() == 1


def test_prune_keeps_unsynced_and_recent_synced(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    with BucketStore(tmp_path / "edge.db") as s:
        for i in range(10):
            s.write_observation(_obs(start=B0 + timedelta(minutes=15 * i)))
        # sync the first 8, leave 2 unsynced
        keys = [(r["zone_version_id"], r["bucket_start"]) for r in s.unsynced_observations()[:8]]
        s.mark_observations_synced(keys, now)

        deleted = s.prune_synced(keep=3)
        assert deleted == 5  # 8 synced - 3 kept
        assert s.pending_count() == 2  # unsynced untouched
        assert len(s.unsynced_observations()) == 2


def test_integrity_check_rejects_a_non_database_file(tmp_path: Path) -> None:
    bad = tmp_path / "not.db"
    bad.write_bytes(b"this is not sqlite" * 100)
    with pytest.raises(IntegrityError):
        BucketStore(bad)


def test_schema_version_is_recorded(tmp_path: Path) -> None:
    with BucketStore(tmp_path / "edge.db") as s:
        assert s.schema_version() == 1
