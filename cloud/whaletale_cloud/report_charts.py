"""Server-rendered SVG for the PDF report (spec 11: "server-rendered SVG for
PDF"). No JS, no external chart library - these are a handful of rects and text.

Palette follows the Section 13 direction: a daytime leasing document, not a NOC
screen. Muted ink and teal on paper, brick red only for anomalies.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from html import escape

INK = "#23201b"
RULE = "#d8d3c8"
BAR = "#3d5a5b"
BAR_MUTED = "#b8c3c0"
ANOMALY = "#a8452f"
VACANT = "#efe9dd"
PAPER = "#ffffff"


def bar_chart(
    values: Sequence[tuple[str, float]],
    *,
    width: int = 640,
    height: int = 160,
    highlight: set[str] | None = None,
) -> str:
    highlight = highlight or set()
    pad_l, pad_r, pad_t, pad_b = 8, 8, 8, 22
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    peak = max((v for _, v in values), default=0) or 1
    n = len(values)
    slot = plot_w / n
    bar_w = slot * 0.66

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'font-family="Georgia, \'Times New Roman\', serif" role="img">'
    ]
    parts.append(
        f'<line x1="{pad_l}" y1="{pad_t + plot_h}" x2="{width - pad_r}" '
        f'y2="{pad_t + plot_h}" stroke="{RULE}" stroke-width="1"/>'
    )
    for i, (label, value) in enumerate(values):
        h = (value / peak) * plot_h
        x = pad_l + i * slot + (slot - bar_w) / 2
        y = pad_t + plot_h - h
        fill = ANOMALY if label in highlight else BAR
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{h:.1f}" fill="{fill}"/>'
        )
        parts.append(
            f'<text x="{x + bar_w / 2:.1f}" y="{height - 6}" text-anchor="middle" '
            f'font-size="10" fill="{INK}">{escape(label)}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def occupancy_timeline(
    spans: Sequence[tuple[str | None, date, date]],
    period_start: date,
    period_end: date,
    *,
    width: int = 640,
    height: int = 64,
) -> str:
    total_days = (period_end - period_start).days + 1 or 1
    px_per_day = width / total_days
    y, band_h = 8, 30

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'font-family="Georgia, \'Times New Roman\', serif" role="img">'
    ]
    for name, s, e in spans:
        x = (s - period_start).days * px_per_day
        w = ((e - s).days + 1) * px_per_day
        if name is None:
            parts.append(
                f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="{band_h}" '
                f'fill="{VACANT}" stroke="{RULE}"/>'
                f'<text x="{x + w / 2:.1f}" y="{y + band_h / 2 + 4:.1f}" text-anchor="middle" '
                f'font-size="10" fill="{INK}" opacity="0.6">vacant</text>'
            )
        else:
            parts.append(
                f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="{band_h}" fill="{BAR}"/>'
                f'<text x="{x + w / 2:.1f}" y="{y + band_h / 2 + 4:.1f}" text-anchor="middle" '
                f'font-size="10" fill="{PAPER}">{escape(name)}</text>'
            )
    parts.append(
        f'<text x="0" y="{height - 4}" font-size="10" fill="{INK}">'
        f"{period_start.isoformat()}</text>"
        f'<text x="{width}" y="{height - 4}" text-anchor="end" font-size="10" fill="{INK}">'
        f"{period_end.isoformat()}</text>"
    )
    parts.append("</svg>")
    return "".join(parts)


def peer_strip(rank: int, peer_count: int, *, width: int = 200, height: int = 24) -> str:
    """A small rank-among-peers indicator: dots, the space's own filled."""
    if peer_count <= 0:
        return ""
    gap = width / max(peer_count, 1)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img">']
    for i in range(peer_count):
        cx = gap * i + gap / 2
        fill = ANOMALY if i == rank - 1 else BAR_MUTED
        r = 6 if i == rank - 1 else 4
        parts.append(f'<circle cx="{cx:.1f}" cy="{height / 2}" r="{r}" fill="{fill}"/>')
    parts.append("</svg>")
    return "".join(parts)
