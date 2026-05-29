"""Password hashing and verification using bcrypt.

Direct bcrypt usage (no passlib) — passlib has compatibility issues with
bcrypt >= 4.x. bcrypt is the standard for password storage; cost factor 12
is the OWASP recommendation for 2024-2026.
"""
from __future__ import annotations

import bcrypt

BCRYPT_ROUNDS = 12


def hash_password(plain: str) -> str:
    """Hash a plaintext password. Returns a UTF-8 string suitable for DB storage."""
    if not plain:
        raise ValueError("password must be non-empty")
    salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    return bcrypt.hashpw(plain.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time verification. Returns False on any error (never raises)."""
    if not plain or not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False
