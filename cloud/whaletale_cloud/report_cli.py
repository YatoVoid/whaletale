"""`whaletale-report` - generate the demo one-pager from seeded data.

    uv run whaletale-report --out /tmp/report        # writes report.html + report.pdf
    uv run whaletale-report --seed --out /tmp/report  # (re)seed first

Needs DATABASE_URL pointing at a Postgres with the schema migrated.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from whaletale_cloud.db import session_scope
from whaletale_cloud.report import build_report, demo_period
from whaletale_cloud.report_render import render_html, render_pdf
from whaletale_cloud.seed import seed_demo


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="whaletale-report")
    p.add_argument("--out", default="report", help="output path prefix (writes .html and .pdf)")
    p.add_argument("--seed", action="store_true", help="seed the demo site first")
    p.add_argument("--html-only", action="store_true", help="skip the PDF")
    args = p.parse_args(argv)

    out = Path(args.out)
    with session_scope() as session:
        if args.seed:
            seed_demo(session)
            session.flush()
        try:
            space_id, start, end = demo_period(session)
        except LookupError as exc:
            print(f"error: {exc}. Run with --seed.", file=sys.stderr)
            return 1
        data = build_report(session, space_id, start, end)

    out.parent.mkdir(parents=True, exist_ok=True)
    html_path = out.with_suffix(".html")
    html_path.write_text(render_html(data), encoding="utf-8")
    print(f"wrote {html_path}")
    if not args.html_only:
        pdf_path = out.with_suffix(".pdf")
        pdf_path.write_bytes(render_pdf(data))
        print(f"wrote {pdf_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
