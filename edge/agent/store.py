"""Local SQLite store for 15-minute rollups, buffered until the sync client
ships them (spec 6.2 step 7, 8.4).

Only aggregates are written - never a frame, crop, box, embedding, or track path
(spec 6.3). The `zone_version_id` / `site_id` keys are the cloud's; on the edge
they come from the paired config (M7), so a synced row is a straight upsert.

Durability (spec 8.4): WAL mode, an integrity check on open, upsert on the
`(zone_version_id, bucket_start)` key so a re-processed bucket overwrites rather
than duplicates, and `prune_synced` to rotate the oldest shipped rows when the
disk gets tight.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS observations (
    zone_version_id    TEXT NOT NULL,
    bucket_start       TEXT NOT NULL,   -- ISO-8601 UTC
    bucket_end         TEXT NOT NULL,
    entries            INTEGER NOT NULL,
    exits              INTEGER NOT NULL,
    peak_occupancy     INTEGER NOT NULL,
    occupied_seconds   REAL NOT NULL,
    dwell_p50_seconds  REAL NOT NULL,
    dwell_p90_seconds  REAL NOT NULL,
    passersby          INTEGER NOT NULL,
    capture_events     INTEGER NOT NULL,
    synced_at          TEXT,            -- NULL until the sync client ships it
    PRIMARY KEY (zone_version_id, bucket_start)
);

CREATE TABLE IF NOT EXISTS site_totals (
    site_id        TEXT NOT NULL,
    bucket_start   TEXT NOT NULL,   -- spec 5.1: 15-minute bucket, end implied
    total_people   INTEGER NOT NULL,
    active_cameras INTEGER NOT NULL,
    synced_at      TEXT,
    PRIMARY KEY (site_id, bucket_start)
);

CREATE INDEX IF NOT EXISTS ix_observations_unsynced
    ON observations (bucket_start) WHERE synced_at IS NULL;
CREATE INDEX IF NOT EXISTS ix_site_totals_unsynced
    ON site_totals (bucket_start) WHERE synced_at IS NULL;
"""


@dataclass(frozen=True)
class ObservationRecord:
    zone_version_id: str
    bucket_start: datetime
    bucket_end: datetime
    entries: int
    exits: int
    peak_occupancy: int
    occupied_seconds: float
    dwell_p50_seconds: float
    dwell_p90_seconds: float
    passersby: int
    capture_events: int


@dataclass(frozen=True)
class SiteTotalRecord:
    site_id: str
    bucket_start: datetime
    total_people: int
    active_cameras: int


class IntegrityError(RuntimeError):
    pass


class BucketStore:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._db = sqlite3.connect(self.path, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        try:
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA synchronous=NORMAL")
            self._db.execute("PRAGMA foreign_keys=ON")
            if self.path != ":memory:":
                row = self._db.execute("PRAGMA integrity_check").fetchone()
                if row[0] != "ok":
                    raise IntegrityError(f"{self.path}: {row[0]}")
        except sqlite3.DatabaseError as exc:
            self._db.close()
            raise IntegrityError(f"{self.path}: {exc}") from exc
        self._db.executescript(_SCHEMA)
        self._db.execute(
            "INSERT INTO meta(key, value) VALUES('schema_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(SCHEMA_VERSION),),
        )

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> BucketStore:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # --- writes -----------------------------------------------------------

    def write_observation(self, rec: ObservationRecord) -> None:
        """Upsert on (zone_version_id, bucket_start). Re-processing a bucket
        overwrites and re-arms it for sync (spec 8.4)."""
        self._db.execute(
            """
            INSERT INTO observations (
                zone_version_id, bucket_start, bucket_end, entries, exits,
                peak_occupancy, occupied_seconds, dwell_p50_seconds,
                dwell_p90_seconds, passersby, capture_events, synced_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?, NULL)
            ON CONFLICT(zone_version_id, bucket_start) DO UPDATE SET
                bucket_end=excluded.bucket_end,
                entries=excluded.entries, exits=excluded.exits,
                peak_occupancy=excluded.peak_occupancy,
                occupied_seconds=excluded.occupied_seconds,
                dwell_p50_seconds=excluded.dwell_p50_seconds,
                dwell_p90_seconds=excluded.dwell_p90_seconds,
                passersby=excluded.passersby,
                capture_events=excluded.capture_events,
                synced_at=NULL
            """,
            (
                rec.zone_version_id,
                _iso(rec.bucket_start),
                _iso(rec.bucket_end),
                rec.entries,
                rec.exits,
                rec.peak_occupancy,
                rec.occupied_seconds,
                rec.dwell_p50_seconds,
                rec.dwell_p90_seconds,
                rec.passersby,
                rec.capture_events,
            ),
        )

    def write_site_total(self, rec: SiteTotalRecord) -> None:
        self._db.execute(
            """
            INSERT INTO site_totals (
                site_id, bucket_start, total_people, active_cameras, synced_at
            ) VALUES (?,?,?,?, NULL)
            ON CONFLICT(site_id, bucket_start) DO UPDATE SET
                total_people=excluded.total_people,
                active_cameras=excluded.active_cameras,
                synced_at=NULL
            """,
            (
                rec.site_id,
                _iso(rec.bucket_start),
                rec.total_people,
                rec.active_cameras,
            ),
        )

    # --- sync-side reads -------------------------------------------------

    def unsynced_observations(self, limit: int = 500) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM observations WHERE synced_at IS NULL ORDER BY bucket_start LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def unsynced_site_totals(self, limit: int = 500) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM site_totals WHERE synced_at IS NULL ORDER BY bucket_start LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def mark_observations_synced(self, keys: Iterable[tuple[str, str]], when: datetime) -> None:
        self._db.executemany(
            "UPDATE observations SET synced_at=? WHERE zone_version_id=? AND bucket_start=?",
            [(_iso(when), zv, bs) for zv, bs in keys],
        )

    def mark_site_totals_synced(self, keys: Iterable[tuple[str, str]], when: datetime) -> None:
        self._db.executemany(
            "UPDATE site_totals SET synced_at=? WHERE site_id=? AND bucket_start=?",
            [(_iso(when), sid, bs) for sid, bs in keys],
        )

    def pending_count(self) -> int:
        o = self._db.execute(
            "SELECT COUNT(*) FROM observations WHERE synced_at IS NULL"
        ).fetchone()[0]
        s = self._db.execute("SELECT COUNT(*) FROM site_totals WHERE synced_at IS NULL").fetchone()[
            0
        ]
        return int(o + s)

    # --- housekeeping --------------------------------------------------

    def prune_synced(self, keep: int = 5000) -> int:
        """Drop the oldest synced observations beyond `keep` rows (spec 8.4
        disk-fill rotation). Never touches unsynced rows. Returns rows deleted."""
        cur = self._db.execute(
            """
            DELETE FROM observations
            WHERE synced_at IS NOT NULL AND rowid NOT IN (
                SELECT rowid FROM observations WHERE synced_at IS NOT NULL
                ORDER BY bucket_start DESC LIMIT ?
            )
            """,
            (keep,),
        )
        return cur.rowcount

    def schema_version(self) -> int:
        row = self._db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        return int(row[0]) if row else 0


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def to_records(zone_version_id: str, buckets: Sequence[Any]) -> list[ObservationRecord]:
    """Convenience: `WallClockBucket` list -> `ObservationRecord` list."""
    out: list[ObservationRecord] = []
    for b in buckets:
        s = b.stats
        out.append(
            ObservationRecord(
                zone_version_id=zone_version_id,
                bucket_start=b.start,
                bucket_end=b.end,
                entries=s.entries,
                exits=s.exits,
                peak_occupancy=s.peak_occupancy,
                occupied_seconds=round(s.occupied_seconds, 1),
                dwell_p50_seconds=round(s.dwell_p50, 1),
                dwell_p90_seconds=round(s.dwell_p90, 1),
                passersby=s.passersby,
                capture_events=s.capture_events,
            )
        )
    return out
