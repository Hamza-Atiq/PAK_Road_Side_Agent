"""Unit tests for password hashing."""
from __future__ import annotations

import pytest

from app.services.security import hash_password, verify_password


def test_hash_produces_bcrypt_format():
    h = hash_password("password123")
    assert h.startswith("$2b$")
    assert len(h) >= 60


def test_round_trip():
    assert verify_password("password123", hash_password("password123")) is True


def test_wrong_password_rejected():
    h = hash_password("right-password")
    assert verify_password("wrong-password", h) is False


def test_two_hashes_of_same_password_differ_but_both_verify():
    """bcrypt uses random salt, so two hashes of the same input must differ."""
    h1 = hash_password("password123")
    h2 = hash_password("password123")
    assert h1 != h2
    assert verify_password("password123", h1) is True
    assert verify_password("password123", h2) is True


def test_empty_password_raises():
    with pytest.raises(ValueError):
        hash_password("")


def test_garbage_hash_returns_false_not_raises():
    assert verify_password("anything", "not-a-bcrypt-hash") is False
    assert verify_password("anything", "") is False
    assert verify_password("", "anything") is False
