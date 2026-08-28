from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from whaletale_cloud.normalization import normalize_space
from whaletale_cloud.seed import SITE_TZ, SeedResult

TZ = ZoneInfo(SITE_TZ)


def _local_day_window(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time(0), tzinfo=TZ).astimezone(UTC)
    return start, start + timedelta(days=1)


def test_report_carries_all_three_comparisons(seeded: tuple[Session, SeedResult]) -> None:
    db, res = seeded
    target_day = res.epoch + timedelta(weeks=5, days=5)  # a Saturday, week 6
    rep = normalize_space(db, res.space_ids["stall-1"], *_local_day_window(target_day))

    assert rep.share_of_site is not None and 0.0 < rep.share_of_site <= 1.0
    assert rep.entries_vs_self.metric == "entries"
    assert rep.entries_vs_self.baseline_n >= 3  # trailing Saturdays with data
    assert rep.peer_rank is not None
    assert rep.peer_rank.peer_count >= 5  # six stalls
    assert 1 <= rep.peer_rank.rank <= rep.peer_rank.peer_count


def test_festival_saturday_is_flagged_as_an_anomaly(seeded: tuple[Session, SeedResult]) -> None:
    db, res = seeded
    assert res.festival_day is not None
    rep = normalize_space(db, res.space_ids["entrance-1"], *_local_day_window(res.festival_day))
    assert rep.entries_vs_self.baseline_n >= 2
    assert rep.entries_vs_self.z_score is not None and rep.entries_vs_self.z_score > 2
    assert rep.entries_vs_self.is_anomaly


def test_a_normal_day_is_not_an_anomaly(seeded: tuple[Session, SeedResult]) -> None:
    db, res = seeded
    target_day = res.epoch + timedelta(weeks=5, days=2)  # a Wednesday, week 6
    rep = normalize_space(db, res.space_ids["entrance-1"], *_local_day_window(target_day))
    assert not rep.entries_vs_self.is_anomaly


def test_excluded_day_is_dropped_from_the_baseline(seeded: tuple[Session, SeedResult]) -> None:
    db, res = seeded
    assert res.closure_day is not None
    # Four weeks after the closure day: its trailing baseline includes the
    # closure day, which must be excluded.
    target_day = res.closure_day + timedelta(weeks=4)
    rep = normalize_space(
        db, res.space_ids["stall-1"], *_local_day_window(target_day), baseline_weeks=4
    )
    assert rep.entries_vs_self.baseline_n <= 3  # one of four trailing weeks removed


def test_peer_rank_is_consistent_across_the_kind(seeded: tuple[Session, SeedResult]) -> None:
    db, res = seeded
    window = _local_day_window(res.epoch + timedelta(weeks=2, days=1))
    ranks = {
        name: normalize_space(db, res.space_ids[name], *window).peer_rank
        for name in ("stall-1", "stall-2", "stall-3", "stall-4", "stall-5", "stall-6")
    }
    present = [r for r in ranks.values() if r is not None]
    assert present
    assert len({r.peer_count for r in present}) == 1  # same peer set for every stall
    assert sorted(r.rank for r in present) == list(range(1, len(present) + 1))
