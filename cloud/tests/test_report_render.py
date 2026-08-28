from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from whaletale_cloud.normalization import PeerRank, SelfComparison
from whaletale_cloud.report import (
    AnomalyRow,
    DayBar,
    HourBar,
    OccupancySpan,
    ReportData,
)
from whaletale_cloud.report_charts import bar_chart, occupancy_timeline, peer_strip
from whaletale_cloud.report_render import render_html, render_pdf


def _cmp(value: float, *, anomaly: bool = False) -> SelfComparison:
    return SelfComparison(
        metric="entries",
        value=value,
        baseline_mean=value * 0.8,
        baseline_stdev=value * 0.05,
        baseline_n=4,
        z_score=3.5 if anomaly else 0.4,
        is_anomaly=anomaly,
    )


def _sample() -> ReportData:
    start = date(2026, 6, 22)
    return ReportData(
        site_name="Cedar Street Market",
        site_timezone="America/Chicago",
        space_name="Stall 3",
        space_kind="stall",
        period_start=start,
        period_end=start + timedelta(days=6),
        generated_at=datetime(2026, 8, 28, 2, 0, tzinfo=UTC),
        entries=1964,
        traffic_share=0.049,
        capture_rate=0.461,
        median_dwell_seconds=45.0,
        peer_rank=PeerRank(kind="stall", capture_rate=0.461, rank=3, peer_count=6, percentile=0.6),  # type: ignore[arg-type]
        entries_vs_self=_cmp(1964, anomaly=True),
        capture_rate_vs_self=_cmp(0.461),
        degraded_bucket_count=2,
        low_confidence_bucket_count=3,
        hourly=[HourBar(h, max(0, 40 - abs(14 - h) * 3)) for h in range(24)],
        daily=[
            DayBar(i, lbl, 200 + i * 30)
            for i, lbl in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
        ],
        occupancy=[
            OccupancySpan(None, start, start + timedelta(days=4)),
            OccupancySpan("The Pickle Cart", start + timedelta(days=5), start + timedelta(days=6)),
        ],
        anomalies=[
            AnomalyRow(
                day=start + timedelta(days=5),
                entries_value=823,
                entries_baseline_mean=315.0,
                entries_z=11.6,
                annotation_kind="event",
                annotation_label="Cedar Street Fall Festival",
            )
        ],
    )


def test_html_carries_the_headline_facts_with_units() -> None:
    html = render_html(_sample())
    assert html.startswith("<!doctype html>")
    assert "Stall 3" in html
    assert "Cedar Street Market" in html
    assert "1,964" in html
    assert "4.9%" in html  # traffic share
    assert "46.1%" in html  # capture rate
    assert "45s" in html  # median dwell
    assert "rank 3 of 6 stalls" in html
    assert "flagged as anomalous" in html
    assert "Cedar Street Fall Festival" in html
    assert "docs/metrics.md" in html
    assert "degraded" in html  # the 2-bucket note
    assert "<svg" in html


def test_html_handles_an_empty_anomaly_list() -> None:
    data = _sample()
    data = ReportData(**{**data.__dict__, "anomalies": []})
    html = render_html(data)
    assert "No days in this period" in html


def test_pdf_is_a_pdf() -> None:
    pdf = render_pdf(_sample())
    assert pdf[:5] == b"%PDF-"
    assert len(pdf) > 2000


def test_bar_chart_has_one_rect_per_value_and_highlights() -> None:
    svg = bar_chart([("Mon", 10), ("Tue", 20), ("Wed", 5)], highlight={"Tue"})
    assert svg.startswith("<svg")
    assert svg.count("<rect") == 3
    assert "#a8452f" in svg  # anomaly colour used for the highlighted bar


def test_occupancy_timeline_marks_vacant() -> None:
    svg = occupancy_timeline(
        [
            (None, date(2026, 6, 1), date(2026, 6, 3)),
            ("Tenant", date(2026, 6, 4), date(2026, 6, 7)),
        ],
        date(2026, 6, 1),
        date(2026, 6, 7),
    )
    assert "vacant" in svg
    assert "Tenant" in svg


def test_peer_strip_draws_a_dot_per_peer() -> None:
    assert peer_strip(2, 5).count("<circle") == 5
    assert peer_strip(1, 0) == ""
