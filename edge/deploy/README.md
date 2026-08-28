# Edge box deployment

Two systemd services on the on-prem mini PC:

| Unit | Job |
|---|---|
| `whaletale-agent.service` | decode RTSP for every camera, one batched inference per tick, write 15-minute rollups to the local SQLite buffer |
| `whaletale-sync.service` | every 60s, ship unsynced rollups to the cloud and post a heartbeat |

## Install

```bash
sudo useradd --system --home /var/lib/whaletale --shell /usr/sbin/nologin whaletale
sudo mkdir -p /opt/whaletale /etc/whaletale /var/lib/whaletale
sudo chown whaletale:whaletale /var/lib/whaletale

# app: a venv with the edge package
sudo python3.12 -m venv /opt/whaletale/venv
sudo /opt/whaletale/venv/bin/pip install /path/to/whaletale-edge

# config
sudo cp deploy/agent.env.example /etc/whaletale/agent.env
sudo cp site.example.json /etc/whaletale/site.json     # then edit: real site_id,
                                                       # pairing token, RTSP URLs,
                                                       # zone_version_ids, polygons
sudo chmod 600 /etc/whaletale/site.json                # RTSP creds + pairing token

sudo cp deploy/whaletale-agent.service deploy/whaletale-sync.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now whaletale-agent whaletale-sync
```

## Operating

- `journalctl -u whaletale-agent -f` - live agent log (camera errors, model load).
- `systemctl status whaletale-sync` - last push result.
- The agent keeps collecting through a WAN outage; the sync service catches up
  when the link returns (`synced_at IS NULL` is the watermark).
- `whaletale-sync --config /etc/whaletale/site.json --dry-run` prints what is
  currently buffered without sending it.

## Not yet wired

`WatchdogSec` / `sd_notify` liveness pings, and the perceptual-hash camera-moved
check (spec 8.1), land in M8/M10.
