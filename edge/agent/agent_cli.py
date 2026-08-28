"""`whaletale-agent` - the multi-camera edge daemon (spec M4).

    whaletale-agent --config site.json          # run until Ctrl-C / SIGTERM
    whaletale-agent --config site.json --seconds 60
    whaletale-agent --config site.json --warm    # load the model and exit

Writes 15-minute rollups to the local SQLite buffer (`EDGE_SQLITE_PATH`); the
sync client (`whaletale-sync`) ships them.
"""

from __future__ import annotations

import argparse
import signal
import sys
import time
from types import FrameType

from agent import __version__
from agent.config import Config, ConfigError
from agent.siteconfig import SiteConfigError, load_site_config
from agent.store import BucketStore, IntegrityError


def _fail(msg: str) -> int:
    print(f"error: {msg}", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="whaletale-agent")
    p.add_argument("--config", required=True, help="path to the site config JSON")
    p.add_argument("--sqlite", default=None, help="override EDGE_SQLITE_PATH")
    p.add_argument("--fps", type=float, default=None)
    p.add_argument("--device", default=None, choices=["cpu", "cuda"])
    p.add_argument("--model", default=None)
    p.add_argument("--seconds", type=float, default=0.0, help="stop after N seconds (0 = forever)")
    p.add_argument("--warm", action="store_true", help="load the model and exit")
    args = p.parse_args(argv)

    try:
        cfg = Config.from_env()
    except ConfigError as exc:
        return _fail(str(exc))
    fps = args.fps if args.fps is not None else cfg.target_fps
    device = args.device or cfg.device
    model = args.model or cfg.model_id
    if fps <= 0:
        return _fail(f"--fps must be > 0, got {fps}")

    try:
        site = load_site_config(args.config)
    except SiteConfigError as exc:
        return _fail(str(exc))

    from agent.detect import PersonDetector

    print(
        f"whaletale-agent {__version__}  site={site.site_id}  "
        f"cameras={len(site.cameras)}  zones={site.zone_count}",
        flush=True,
    )
    load_start = time.monotonic()
    try:
        detector = PersonDetector(
            model_id=model,
            device=device,
            hf_cache=cfg.hf_cache,
            score_threshold=cfg.score_threshold,
        )
    except Exception as exc:  # model load fails many ways
        return _fail_1(f"could not load model {model!r}: {exc}")
    print(f"model ready in {time.monotonic() - load_start:.1f}s", flush=True)
    if args.warm:
        return 0

    from agent.pipeline import MultiCameraPipeline

    try:
        store = BucketStore(args.sqlite or cfg.sqlite_path)
    except IntegrityError as exc:
        return _fail_1(str(exc))

    pipeline = MultiCameraPipeline(
        site,
        detector,
        store,
        fps=fps,
        min_dwell_seconds=cfg.min_dwell_seconds,
        exit_margin=cfg.exit_margin_frac,
        catchment_margin=cfg.catchment_frac,
        bucket_seconds=int(cfg.bucket_seconds),
    )

    stop_at = time.monotonic() + args.seconds if args.seconds else None
    stopping = {"flag": False}

    def _handle(_sig: int, _frame: FrameType | None) -> None:
        stopping["flag"] = True

    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)

    def should_stop() -> bool:
        if stopping["flag"]:
            return True
        return stop_at is not None and time.monotonic() >= stop_at

    print("running; Ctrl-C to stop", flush=True)
    try:
        pipeline.run(should_stop)
    finally:
        pipeline.close()
        pending = store.pending_count()
        store.close()

    for cam, err in pipeline.worker_errors.items():
        print(f"camera {cam}: {err}", file=sys.stderr)
    print(f"stopped. {pending} bucket rows pending sync.", flush=True)
    return 1 if pipeline.worker_errors and pending == 0 else 0


def _fail_1(msg: str) -> int:
    print(f"error: {msg}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
