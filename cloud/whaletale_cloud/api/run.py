"""`whaletale-api` - run the ingest API with uvicorn.

DATABASE_URL=... uv run whaletale-api --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="whaletale-api")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--reload", action="store_true")
    args = p.parse_args(argv)

    import uvicorn

    uvicorn.run(
        "whaletale_cloud.api.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
