"""WS-Discovery probe for ONVIF cameras on the LAN (spec 7).

Returns manufacturer, model, and IP from the multicast Hello/Probe scopes. It
does not need credentials and does not touch the video stream - that is the
validation gate's job. Cameras on a separate VLAN will not answer; the manual
RTSP path in `whaletale-onboard` covers those.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import unquote, urlparse

_NVT_TYPE = "tdn:NetworkVideoTransmitter"


@dataclass(frozen=True)
class DiscoveredCamera:
    ip: str
    xaddr: str  # the device service URL
    manufacturer: str | None
    model: str | None
    scopes: tuple[str, ...]

    @property
    def label(self) -> str:
        parts = [p for p in (self.manufacturer, self.model) if p]
        return " ".join(parts) if parts else self.ip


def discover(timeout: float = 4.0) -> list[DiscoveredCamera]:
    """Multicast-probe for ONVIF NVTs. Blocks for roughly `timeout` seconds."""
    from wsdiscovery import QName
    from wsdiscovery.discovery import ThreadedWSDiscovery

    wsd = ThreadedWSDiscovery()
    wsd.start()
    try:
        services = wsd.searchServices(
            types=[QName("http://www.onvif.org/ver10/network/wsdl", "NetworkVideoTransmitter")],
            timeout=int(timeout),
        )
    finally:
        wsd.stop()

    out: list[DiscoveredCamera] = []
    seen: set[str] = set()
    for svc in services:
        xaddrs = list(svc.getXAddrs())
        if not xaddrs:
            continue
        xaddr = xaddrs[0]
        ip = urlparse(xaddr).hostname or ""
        if not ip or ip in seen:
            continue
        seen.add(ip)
        scopes = tuple(
            str(s.getValue()) if hasattr(s, "getValue") else str(s) for s in svc.getScopes()
        )
        out.append(
            DiscoveredCamera(
                ip=ip,
                xaddr=xaddr,
                manufacturer=_scope_value(scopes, "name"),
                model=_scope_value(scopes, "hardware"),
                scopes=scopes,
            )
        )
    return out


def _scope_value(scopes: tuple[str, ...], key: str) -> str | None:
    """Pull `onvif://www.onvif.org/<key>/<value>` out of the scope list."""
    pat = re.compile(rf"onvif://www\.onvif\.org/{re.escape(key)}/(.+)$", re.IGNORECASE)
    for s in scopes:
        m = pat.search(s)
        if m:
            return unquote(m.group(1)).replace("_", " ").strip() or None
    return None


def rtsp_uri_via_onvif(xaddr: str, username: str, password: str) -> str | None:
    """Ask the device for its first RTSP stream URI. Needs the optional
    `onvif` extra; returns None if it is not installed or the query fails."""
    try:
        from onvif import ONVIFCamera
    except ImportError:
        return None
    try:
        parsed = urlparse(xaddr)
        cam = ONVIFCamera(parsed.hostname, parsed.port or 80, username, password)
        media = cam.create_media_service()
        profiles = media.GetProfiles()
        if not profiles:
            return None
        req = media.create_type("GetStreamUri")
        req.ProfileToken = profiles[0].token
        req.StreamSetup = {
            "Stream": "RTP-Unicast",
            "Transport": {"Protocol": "RTSP"},
        }
        uri = media.GetStreamUri(req)
        return str(uri.Uri)
    except Exception:
        return None
