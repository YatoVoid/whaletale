"""Render a `ReportData` to HTML, and HTML to PDF with WeasyPrint (spec 11:
"Do not build PDF layout by hand")."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from whaletale_cloud.config import settings
from whaletale_cloud.report import ReportData
from whaletale_cloud.report_charts import bar_chart, occupancy_timeline, peer_strip

_TEMPLATES = Path(__file__).parent / "templates"
_env = Environment(
    loader=FileSystemLoader(_TEMPLATES),
    autoescape=select_autoescape(["html"]),
)


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{x * 100:.1f}%"


def _dur(seconds: float) -> str:
    seconds = round(seconds)
    if seconds < 60:
        return f"{seconds}s"
    return f"{seconds // 60}m {seconds % 60:02d}s"


def _zlabel(z: float) -> str:
    return f"{z:+.1f} SD"


def render_html(data: ReportData) -> str:
    template = _env.get_template("report.html")
    hourly_svg = bar_chart([(f"{h.hour:02d}", h.entries) for h in data.hourly if 6 <= h.hour <= 21])
    daily_svg = bar_chart(
        [(b.label, b.entries) for b in data.daily],
        highlight={a.day.strftime("%a") for a in data.anomalies},
    )
    occ_svg = occupancy_timeline(
        [(s.occupant_name, s.start, s.end) for s in data.occupancy],
        data.period_start,
        data.period_end,
    )
    return template.render(
        d=data,
        hourly_svg=hourly_svg,
        daily_svg=daily_svg,
        occupancy_svg=occ_svg,
        sigma=f"{settings.anomaly_sigma:g}",
        pct=_pct,
        dur=_dur,
        zlabel=_zlabel,
        peer_strip=peer_strip,
    )


def render_pdf(data: ReportData) -> bytes:
    from weasyprint import HTML

    return HTML(string=render_html(data)).write_pdf()  # type: ignore[no-any-return]
