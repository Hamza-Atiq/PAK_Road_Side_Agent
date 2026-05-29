"""Unit tests for the JWT service. No DB required."""
from __future__ import annotations

import time
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest

from app.services.jwt_service import (
    InvalidTokenError,
    decode_token,
    encode_access_token,
    encode_refresh_token,
)


def test_access_token_round_trip():
    uid = uuid.uuid4()
    token = encode_access_token(user_id=uid, role="customer", phone="+15551234567")
    payload = decode_token(token, expected_type="access")
    assert payload.sub == str(uid)
    assert payload.role == "customer"
    assert payload.phone == "+15551234567"
    assert payload.token_type == "access"
    assert payload.exp > payload.iat


def test_refresh_token_has_correct_type():
    uid = uuid.uuid4()
    token = encode_refresh_token(user_id=uid, role="provider", phone="+15551234567")
    payload = decode_token(token, expected_type="refresh")
    assert payload.token_type == "refresh"


def test_refresh_token_rejected_as_access():
    """Using a refresh token where an access token is expected must fail."""
    token = encode_refresh_token(user_id=uuid.uuid4(), role="customer", phone="+15551234567")
    with pytest.raises(InvalidTokenError, match="wrong token type"):
        decode_token(token, expected_type="access")


def test_access_token_rejected_as_refresh():
    token = encode_access_token(user_id=uuid.uuid4(), role="customer", phone="+15551234567")
    with pytest.raises(InvalidTokenError, match="wrong token type"):
        decode_token(token, expected_type="refresh")


def test_garbage_token_rejected():
    with pytest.raises(InvalidTokenError):
        decode_token("not.a.token", expected_type="access")
    with pytest.raises(InvalidTokenError):
        decode_token("eyJhbGciOiJub25lIn0..", expected_type="access")


def test_token_signed_with_wrong_secret_rejected():
    """Tokens signed with a different key must not validate."""
    from jose import jwt
    payload = {
        "sub": str(uuid.uuid4()), "role": "customer", "phone": "+15551234567",
        "token_type": "access", "jti": str(uuid.uuid4()),
        "iat": int(time.time()), "exp": int(time.time()) + 60,
    }
    forged = jwt.encode(payload, "different-secret-32-chars-min-ok-here", algorithm="HS256")
    with pytest.raises(InvalidTokenError):
        decode_token(forged, expected_type="access")


def test_expired_token_rejected():
    """A token whose exp is in the past must not validate."""
    from app.services.jwt_service import _build_payload, settings
    from jose import jwt
    payload = _build_payload(
        user_id=uuid.uuid4(), role="customer", phone="+15551234567",
        token_type="access", expires_in=timedelta(seconds=-10),
    )
    expired = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    with pytest.raises(InvalidTokenError):
        decode_token(expired, expected_type="access")
