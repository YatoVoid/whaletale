"""`whaletale-sync` - ship buffered rollups to the cloud (spec M4).

whaletale-sync --config site.json --once
whaletale-sync --config site.json --interval 60      # loop
whaletale-sync --config site.json --dry-run          # print the payload, send nothing
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from agent.config import Config, ConfigError
from agent.siteconfig import SiteConfigError, load_site_config
from agent.store import BucketStore, IntegrityError
from sync.client import SyncClient


def _fail(msg: str, code: int = 2) -> int:
    print(f"error: {msg}", file=sys.stderr)
    return code


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="whaletale-sync")
    p.add_argument("--config", required=True)
    p.add_argument("--sqlite", default=None)
    p.add_argument("--once", action="store_true", help="push once and exit")
    p.add_argument("--interval", type=float, default=60.0, help="loop interval seconds")
    p.add_argument("--dry-run", action="store_true", help="print the pending payload, send nothing")
    p.add_argument("--no-heartbeat", action="store_true")
    args = p.parse_args(argv)

    try:
        cfg = Config.from_env()
    except ConfigError as exc:
        return _fail(str(exc))
    try:
        site = load_site_config(args.config)
    except SiteConfigError as exc:
        return _fail(str(exc))
    try:
        store = BucketStore(args.sqlite or cfg.sqlite_path)
    except IntegrityError as exc:
        return _fail(str(exc), 1)

    client = SyncClient(
        store,
        site.cloud_url or cfg.cloud_url,
        site.site_id,
        site.pairing_token or cfg.pairing_token,
    )

    if args.dry_run:
        pending = {
            "observations": store.unsynced_observations(),
            "site_totals": store.unsynced_site_totals(),
        }
        print(json.dumps(pending, indent=2, default=str))
        store.close()
        return 0

    try:
        while True:
            r = client.drain()
            if r.ok:
                print(
                    f"pushed {r.observations_sent} observations, {r.site_totals_sent} site totals",
                    flush=True,
                )
            else:
                print(f"push failed: {r.error} (will retry)", file=sys.stderr, flush=True)
            if not args.no_heartbeat:
                hb = client.heartbeat(store.camera_health())
                if not hb.ok:
                    print(f"heartbeat failed: {hb.error}", file=sys.stderr, flush=True)
            if args.once:
                store.close()
                return 0 if r.ok else 1
            time.sleep(max(1.0, args.interval))
    except KeyboardInterrupt:
        store.close()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
