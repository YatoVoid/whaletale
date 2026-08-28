"""Pair an edge box to a site, returning the one-time raw token.

Used by tests now and by the M7 onboarding wizard later. Not an HTTP endpoint -
pairing happens in the operator console, not over the ingest API.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from whaletale_cloud import models as m
from whaletale_cloud.api.security import hash_token, new_pairing_token


def pair_edge_box(
    session: Session, site_id: UUID, name: str | None = None
) -> tuple[m.EdgeBox, str]:
    raw = new_pairing_token()
    box = m.EdgeBox(site_id=site_id, name=name, token_hash=hash_token(raw))
    session.add(box)
    session.flush()
    return box, raw
