"""Symmetric encryption for sensitive at-rest payloads.

Used by `SecurityEvent.raw_input` so that captured prompt-injection attempts
are never readable in plain text by anyone with DB access. Only the running
app (with the secret key) can decrypt them for security review.

Implementation: Fernet (AES-128-CBC + HMAC-SHA256) from the `cryptography`
library. The key is derived from `settings.ENCRYPTION_KEY` if set, otherwise
deterministically from `settings.JWT_SECRET_KEY` so dev environments work
without extra config. Production should set ENCRYPTION_KEY explicitly.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

log = logging.getLogger(__name__)


def _derive_key() -> bytes:
    """32-byte urlsafe base64 key, either from env or derived from JWT secret."""
    explicit = os.environ.get("ENCRYPTION_KEY", "").strip()
    if explicit:
        # Allow either a raw Fernet key (44-char urlsafe-b64) or a passphrase
        if len(explicit) == 44 and explicit.endswith("="):
            return explicit.encode("ascii")
        digest = hashlib.sha256(explicit.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest)
    # Dev/test fallback: derive deterministically from JWT secret so the key
    # is stable across restarts of the same install.
    digest = hashlib.sha256(
        (settings.JWT_SECRET_KEY + ":encryption").encode("utf-8")
    ).digest()
    return base64.urlsafe_b64encode(digest)


_fernet = Fernet(_derive_key())


def encrypt_str(plaintext: str) -> str:
    """Encrypt a string. Returns a urlsafe-base64 token suitable for TEXT storage."""
    if plaintext is None:
        raise ValueError("plaintext must not be None")
    return _fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_str(token: str) -> str:
    """Decrypt a token. Raises InvalidToken if the token is tampered/invalid."""
    try:
        return _fernet.decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken:
        log.warning("decryption_failed: invalid token (key rotated or data tampered)")
        raise


def try_decrypt(token: str) -> str | None:
    """Best-effort decrypt; returns None on failure (for read-only display use)."""
    try:
        return decrypt_str(token)
    except InvalidToken:
        return None
