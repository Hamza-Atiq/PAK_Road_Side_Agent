"""Unit tests for phone E.164 normalization in auth schemas."""
from __future__ import annotations

import pytest

from app.schemas.auth import RegisterRequest, _normalize_phone


@pytest.mark.parametrize("raw,expected", [
    ("+1 555 123 4567", "+15551234567"),
    ("+15551234567", "+15551234567"),
    ("+44 20 7946 0958", "+442079460958"),
    ("+92 300 1234567", "+923001234567"),
    ("+15550000001", "+15550000001"),  # fictional NANP, allowed
])
def test_phone_normalizes_to_e164(raw, expected):
    assert _normalize_phone(raw) == expected


@pytest.mark.parametrize("raw", ["notaphone", "12345", "", "abc-def-ghij"])
def test_invalid_phone_rejected(raw):
    with pytest.raises(ValueError):
        _normalize_phone(raw)


def test_register_request_normalizes_phone():
    r = RegisterRequest(
        phone="+1 555 123 4567",
        name="Alice",
        password="password123",
        role="customer",
    )
    assert r.phone == "+15551234567"


def test_register_request_rejects_admin_role():
    with pytest.raises(Exception, match="admin"):
        RegisterRequest(
            phone="+15551234567",
            name="X",
            password="password123",
            role="admin",
        )


def test_register_request_min_password_length():
    with pytest.raises(Exception):
        RegisterRequest(
            phone="+15551234567", name="X", password="short", role="customer"
        )
