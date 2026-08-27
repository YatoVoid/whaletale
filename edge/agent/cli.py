from __future__ import annotations

import argparse
import sys
import time

from agent import __version__
from agent.aggregate import RunAggregator
from agent.config import Config, ConfigError
from agent.decode import DecodeError, decode_frames
from agent.zones import ground_point, parse_zone


def _parser(cfg: Config) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="whaletale-edge",
        description="M1 pipeline proof: detect people in one hard-coded zone, count entries.",
    )
    p.add_argument("--source", help="video file, rtsp:// URL, or a webcam index (e.g. 0)")
    p.add_argument("--fps", type=float, default=cfg.target_fps, help="target sampled FPS")
    p.add_argument("--device", default=cfg.device, choices=["cpu", "cuda"])
    p.add_argument("--model", default=cfg.model_id)
    p.add_argument(
        "--zone",
        default=None,
        help="'full', 'x1,y1,x2,y2', or omit for the hand-coded default polygon",
    )
    p.add_argument("--seconds", type=float, default=0.0, help="stop after N seconds of stream time")
    p.add_argument("--max-frames", type=int, default=0, help="stop after N sampled frames")
    p.add_argument("--warm", action="store_true", help="download/load the model and exit")
    p.add_argument("--quiet", action="store_true", help="suppress per-interval progress lines")
    return p


def _fail(msg: str) -> int:
    print(f"error: {msg}", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    try:
        cfg = Config.from_env()
    except ConfigError as exc:
        return _fail(str(exc))

    args = _parser(cfg).parse_args(argv)

    # Cheap validation first, so a typo doesn't cost a model download.
    if args.fps <= 0:
        return _fail(f"--fps must be > 0, got {args.fps}")
    if args.seconds < 0:
        return _fail(f"--seconds must be >= 0, got {args.seconds}")
    if args.max_frames < 0:
        return _fail(f"--max-frames must be >= 0, got {args.max_frames}")

    try:
        zone = parse_zone(
            args.zone,
            exit_margin=cfg.exit_margin_frac,
            catchment_margin=cfg.catchment_frac,
        )
    except ValueError as exc:
        return _fail(f"--zone: {exc}")

    if not args.source and not args.warm:
        return _fail("--source is required (unless --warm)")

    # Imported lazily so --help, bad args, and unit tests don't pull in torch.
    from agent.detect import PersonDetector
    from agent.track import GroundPointTracker

    print(f"whaletale-edge {__version__}  model={args.model}  device={args.device}", flush=True)
    load_start = time.monotonic()
    try:
        detector = PersonDetector(
            model_id=args.model,
            device=args.device,
            hf_cache=cfg.hf_cache,
            score_threshold=cfg.score_threshold,
        )
    except Exception as exc:  # model load fails many ways: bad id, no network, disk
        print(f"error: could not load model {args.model!r}: {exc}", file=sys.stderr)
        return 1
    print(f"model ready in {time.monotonic() - load_start:.1f}s", flush=True)
    if args.warm:
        return 0

    agg = RunAggregator(
        zone,
        min_dwell_seconds=cfg.min_dwell_seconds,
        bucket_seconds=cfg.bucket_seconds,
    )
    tracker = GroundPointTracker()

    prev_ids: set[int] = set()
    frames = 0
    detections_total = 0
    last_t = 0.0
    wall_start = time.monotonic()
    next_progress = wall_start + 2.0

    try:
        for t, rgb in decode_frames(args.source, args.fps):
            dets = detector.detect(rgb)
            detections_total += len(dets)
            gps = [ground_point(box) for box, _score in dets]

            live = tracker.update(gps)
            for lost_id in prev_ids - live.keys():
                agg.end_track(lost_id, t)
            agg.update(t, live)
            prev_ids = set(live)

            frames += 1
            last_t = t
            now = time.monotonic()
            if not args.quiet and now >= next_progress:
                fps = frames / (now - wall_start)
                print(
                    f"  t={t:6.1f}s  frames={frames:5d}  people={len(live):2d}  "
                    f"entries={agg.entries_so_far:3d}  pipeline_fps={fps:4.1f}",
                    flush=True,
                )
                next_progress = now + 2.0

            if args.seconds and t >= args.seconds:
                break
            if args.max_frames and frames >= args.max_frames:
                break
    except KeyboardInterrupt:
        print("\ninterrupted", flush=True)
    except DecodeError as exc:
        print(f"\nerror: {exc}", file=sys.stderr)
        return 1

    buckets = agg.finalize(last_t)
    wall_elapsed = time.monotonic() - wall_start
    s = agg.totals()

    print("\n--- run summary ---")
    if frames == 0:
        print("no frames decoded; check --source")
        return 1
    print(f"source            {args.source}")
    print(f"sampled frames    {frames}  over {last_t:.1f}s stream / {wall_elapsed:.1f}s wall")
    print(f"achievable FPS    {frames / wall_elapsed:.2f}  (target {args.fps:.1f})")
    print(f"mean detections   {detections_total / frames:.2f} per frame")
    print(f"zone              {zone.name}")

    if len(buckets) > 1:
        print(f"\nbuckets ({cfg.bucket_seconds:.0f}s each)")
        print("  #  start     entries  passers  capture  occ_s  person_s")
        for b in buckets:
            st = b.stats
            print(
                f"  {b.index:<2d} {b.start:7.1f}s  {st.entries:7d}  {st.passersby:7d}  "
                f"{st.capture_rate:6.0%}  {st.occupied_seconds:5.0f}  {st.person_seconds:8.0f}"
            )
        print("  run totals")

    print(f"entries           {s.entries}")
    print(f"passersby         {s.passersby}")
    print(f"capture rate      {s.capture_rate:.0%}")
    print(f"occupied seconds  {s.occupied_seconds:.1f}")
    print(f"person-seconds    {s.person_seconds:.1f}")
    print(f"dwell p50 / p90   {s.dwell_p50:.1f}s / {s.dwell_p90:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
