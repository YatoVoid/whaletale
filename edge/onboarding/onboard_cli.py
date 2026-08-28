"""`whaletale-onboard` - discover a camera or validate a manual RTSP URL, then
emit a `site.json` camera block with the credentials sealed (spec 7).

    whaletale-onboard --discover
    whaletale-onboard --source rtsp://user:pass@cam/stream1 --name front-hall
    whaletale-onboard --source rtsp://user:pass@cam/stream1 --name front-hall --emit
"""

from __future__ import annotations

import argparse
import json
import sys
from urllib.parse import urlparse, urlunparse

from agent.config import Config, ConfigError
from onboarding.credentials import CredentialError, seal
from onboarding.validation import validate_source


def _fail(msg: str, code: int = 2) -> int:
    print(f"error: {msg}", file=sys.stderr)
    return code


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="whaletale-onboard")
    p.add_argument("--discover", action="store_true", help="WS-Discovery probe for cameras")
    p.add_argument("--timeout", type=float, default=4.0, help="discovery probe seconds")
    p.add_argument("--source", help="RTSP URL / file / webcam index to validate")
    p.add_argument("--name", help="camera name for the emitted block")
    p.add_argument("--zone-version-id", help="cloud zone_version_id for the emitted zone")
    p.add_argument("--emit", action="store_true", help="print a site.json camera block")
    p.add_argument("--no-inference", action="store_true", help="skip the test-inference check")
    args = p.parse_args(argv)

    if args.discover:
        return _run_discover(args.timeout)
    if not args.source:
        return _fail("give --discover or --source")

    try:
        cfg = Config.from_env()
    except ConfigError as exc:
        return _fail(str(exc))

    detector = None
    if not args.no_inference:
        from agent.detect import PersonDetector

        print("loading model for the inference check…", flush=True)
        try:
            detector = PersonDetector(
                model_id=cfg.model_id,
                device=cfg.device,
                hf_cache=cfg.hf_cache,
                score_threshold=cfg.score_threshold,
            )
        except Exception as exc:  # model load fails many ways
            return _fail(f"could not load model: {exc}", 1)

    report = validate_source(args.source, detector)
    print()
    print(report.render())
    if not report.ok:
        return 1

    if args.emit:
        if not args.name:
            return _fail("--emit needs --name")
        print()
        print(json.dumps(_camera_block(args), indent=2))
    return 0


def _run_discover(timeout: float) -> int:
    from onboarding.discovery import discover

    cams = discover(timeout=timeout)
    if not cams:
        print("no cameras answered the probe (VLAN? try --source with a manual URL)")
        return 0
    for c in cams:
        print(f"{c.ip:16}  {c.label}")
        print(f"                  {c.xaddr}")
    return 0


def _camera_block(args: argparse.Namespace) -> dict[str, object]:
    parsed = urlparse(args.source)
    creds = ""
    source_no_creds = args.source
    if parsed.username or parsed.password:
        creds = f"{parsed.username or ''}:{parsed.password or ''}"
        netloc = parsed.hostname or ""
        if parsed.port:
            netloc += f":{parsed.port}"
        source_no_creds = urlunparse(parsed._replace(netloc=netloc))
    try:
        sealed = seal(creds) if creds else ""
    except CredentialError as exc:
        print(f"warning: {exc}; credentials left unsealed", file=sys.stderr)
        sealed = ""

    zone = {
        "zone_version_id": args.zone_version_id or "REPLACE_WITH_CLOUD_ID",
        "polygon": [[0.3, 0.55], [0.7, 0.55], [0.78, 0.92], [0.22, 0.92]],
    }
    return {
        "name": args.name,
        "source": source_no_creds,
        "credentials_sealed": sealed,
        "zones": [zone],
    }


if __name__ == "__main__":
    raise SystemExit(main())
