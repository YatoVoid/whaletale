"""Encrypt RTSP credentials at rest on the edge box (spec 7).

The key is derived from the per-site secret (`WHALETALE_SITE_SECRET`), so the
ciphertext is portable within a site but useless without the secret. Plaintext
credentials never touch the cloud and are never logged. What the cloud (and
`site.json`) hold is the output of `seal()`.
"""

from __future__ import annotations

import base64
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

_INFO = b"whaletale-edge-rtsp-credentials-v1"


class CredentialError(ValueError):
    pass


def _fernet(site_secret: str) -> Fernet:
    if not site_secret:
        raise CredentialError("no site secret; set WHALETALE_SITE_SECRET")
    key = HKDF(algorithm=SHA256(), length=32, salt=None, info=_INFO).derive(site_secret.encode())
    return Fernet(base64.urlsafe_b64encode(key))


def seal(plaintext: str, *, site_secret: str | None = None) -> str:
    secret = site_secret if site_secret is not None else os.getenv("WHALETALE_SITE_SECRET", "")
    return _fernet(secret).encrypt(plaintext.encode()).decode()


def unseal(token: str, *, site_secret: str | None = None) -> str:
    secret = site_secret if site_secret is not None else os.getenv("WHALETALE_SITE_SECRET", "")
    try:
        return _fernet(secret).decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise CredentialError("could not decrypt; wrong site secret or corrupt token") from exc
