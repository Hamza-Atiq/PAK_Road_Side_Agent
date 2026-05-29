"""JWT encode/decode for access and refresh tokens.

Access tokens carry the user identity + role and live 15 minutes.
Refresh tokens are opaque carriers that grant new access tokens for 7 days.
A `token_type` claim prevents using a refresh token where an access token is required.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from jose import JWTError, jwt
from pydantic import BaseModel

from app.config import settings

TokenType = Literal["access", "refresh"]


class TokenPayload(BaseModel):
    """Validated claims pulled out of a JWT."""

    sub: str  # user UUID
    role: str
    phone: str
    token_type: TokenType
    jti: str  # unique token id
    exp: int
    iat: int


class InvalidTokenError(Exception):
    """Raised when a JWT is expired, malformed, or has the wrong type."""


def _build_payload(
    *,
    user_id: uuid.UUID | str,
    role: str,
    phone: str,
    token_type: TokenType,
    expires_in: timedelta,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    return {
        "sub": str(user_id),
        "role": role,
        "phone": phone,
        "token_type": token_type,
        "jti": str(uuid.uuid4()),
        "iat": int(now.timestamp()),
        "exp": int((now + expires_in).timestamp()),
    }


def encode_access_token(*, user_id: uuid.UUID | str, role: str, phone: str) -> str:
    """Short-lived token used as the Authorization header bearer."""
    payload = _build_payload(
        user_id=user_id,
        role=role,
        phone=phone,
        token_type="access",
        expires_in=timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def encode_refresh_token(*, user_id: uuid.UUID | str, role: str, phone: str) -> str:
    """Long-lived token issued in an HttpOnly cookie."""
    payload = _build_payload(
        user_id=user_id,
        role=role,
        phone=phone,
        token_type="refresh",
        expires_in=timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
    )
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str, *, expected_type: TokenType) -> TokenPayload:
    """Validate signature, expiry, and token_type. Raises InvalidTokenError on any failure."""
    try:
        raw = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError as exc:
        raise InvalidTokenError(f"token decode failed: {exc}") from exc

    try:
        payload = TokenPayload.model_validate(raw)
    except Exception as exc:
        raise InvalidTokenError(f"token payload invalid: {exc}") from exc

    if payload.token_type != expected_type:
        raise InvalidTokenError(
            f"wrong token type: expected {expected_type}, got {payload.token_type}"
        )
    return payload
