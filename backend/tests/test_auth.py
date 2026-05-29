"""Integration tests for /api/auth/* endpoints.

These tests require a live PostgreSQL `roadside_test` database with PostGIS.
See conftest.py for setup instructions.
"""
from __future__ import annotations

import pytest

from app.services.twilio_verify import DEV_OTP_CODE


# ----------------------------------------------------------------------
# Register
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_customer_success(client):
    r = await client.post(
        "/api/auth/register",
        json={
            "phone": "+15551112222",
            "name": "Alice",
            "password": "password123",
            "role": "customer",
        },
    )
    assert r.status_code == 201, r.text
    assert "Verification code sent" in r.json()["message"]


@pytest.mark.asyncio
async def test_register_provider_requires_service_type(client):
    r = await client.post(
        "/api/auth/register",
        json={
            "phone": "+15551112223",
            "name": "Bob",
            "password": "password123",
            "role": "provider",
            # no service_type
        },
    )
    assert r.status_code == 400
    assert "service_type" in r.json()["detail"]


@pytest.mark.asyncio
async def test_register_provider_success(client):
    r = await client.post(
        "/api/auth/register",
        json={
            "phone": "+15551112224",
            "name": "Bob",
            "password": "password123",
            "role": "provider",
            "service_type": "mechanic",
            "vehicle_info": "Ford Transit",
        },
    )
    assert r.status_code == 201, r.text


@pytest.mark.asyncio
async def test_register_admin_rejected(client):
    r = await client.post(
        "/api/auth/register",
        json={
            "phone": "+15551112225",
            "name": "Mallory",
            "password": "password123",
            "role": "admin",
        },
    )
    # Pydantic validation catches this -> 422
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_register_duplicate_phone_conflict(client):
    payload = {
        "phone": "+15551112226",
        "name": "Alice",
        "password": "password123",
        "role": "customer",
    }
    r1 = await client.post("/api/auth/register", json=payload)
    assert r1.status_code == 201
    r2 = await client.post("/api/auth/register", json=payload)
    assert r2.status_code == 409


# ----------------------------------------------------------------------
# Login before OTP -> blocked
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_blocked_before_otp_verification(client):
    await client.post(
        "/api/auth/register",
        json={
            "phone": "+15551112227",
            "name": "Alice",
            "password": "password123",
            "role": "customer",
        },
    )
    r = await client.post(
        "/api/auth/login",
        json={"phone": "+15551112227", "password": "password123"},
    )
    assert r.status_code == 403
    assert "not verified" in r.json()["detail"].lower()


# ----------------------------------------------------------------------
# OTP verification + login
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_otp_verify_activates_and_returns_tokens(client):
    await client.post(
        "/api/auth/register",
        json={
            "phone": "+15551112228",
            "name": "Alice",
            "password": "password123",
            "role": "customer",
        },
    )
    r = await client.post(
        "/api/auth/verify-otp",
        json={"phone": "+15551112228", "code": DEV_OTP_CODE},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "access_token" in body
    assert body["user"]["is_active"] is True
    assert body["user"]["is_phone_verified"] is True


@pytest.mark.asyncio
async def test_otp_wrong_code_rejected(client):
    await client.post(
        "/api/auth/register",
        json={
            "phone": "+15551112229",
            "name": "Alice",
            "password": "password123",
            "role": "customer",
        },
    )
    r = await client.post(
        "/api/auth/verify-otp",
        json={"phone": "+15551112229", "code": "999999"},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_login_succeeds_after_otp(client):
    await client.post(
        "/api/auth/register",
        json={
            "phone": "+15551112230",
            "name": "Alice",
            "password": "password123",
            "role": "customer",
        },
    )
    await client.post(
        "/api/auth/verify-otp",
        json={"phone": "+15551112230", "code": DEV_OTP_CODE},
    )
    r = await client.post(
        "/api/auth/login",
        json={"phone": "+15551112230", "password": "password123"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["access_token"]
    assert body["user"]["role"] == "customer"


@pytest.mark.asyncio
async def test_login_wrong_password_unauthorized(client):
    await client.post(
        "/api/auth/register",
        json={
            "phone": "+15551112231",
            "name": "Alice",
            "password": "password123",
            "role": "customer",
        },
    )
    await client.post(
        "/api/auth/verify-otp",
        json={"phone": "+15551112231", "code": DEV_OTP_CODE},
    )
    r = await client.post(
        "/api/auth/login",
        json={"phone": "+15551112231", "password": "wrong-password"},
    )
    assert r.status_code == 401


# ----------------------------------------------------------------------
# /me + role guard
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_me_requires_auth(client):
    r = await client.get("/api/auth/me")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_current_user(client):
    await client.post(
        "/api/auth/register",
        json={
            "phone": "+15551112232",
            "name": "Alice",
            "password": "password123",
            "role": "customer",
        },
    )
    login = await client.post(
        "/api/auth/verify-otp",
        json={"phone": "+15551112232", "code": DEV_OTP_CODE},
    )
    token = login.json()["access_token"]

    r = await client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200
    assert r.json()["phone"] == "+15551112232"


@pytest.mark.asyncio
async def test_me_rejects_bad_token(client):
    r = await client.get(
        "/api/auth/me", headers={"Authorization": "Bearer not.a.real.token"}
    )
    assert r.status_code == 401


# ----------------------------------------------------------------------
# Refresh
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_issues_new_access_token(client):
    await client.post(
        "/api/auth/register",
        json={
            "phone": "+15551112233",
            "name": "Alice",
            "password": "password123",
            "role": "customer",
        },
    )
    verify = await client.post(
        "/api/auth/verify-otp",
        json={"phone": "+15551112233", "code": DEV_OTP_CODE},
    )
    assert verify.status_code == 200
    # cookie should now be set on the client; calling /refresh uses it
    r = await client.post("/api/auth/refresh")
    assert r.status_code == 200, r.text
    assert "access_token" in r.json()


@pytest.mark.asyncio
async def test_refresh_without_cookie_unauthorized(client):
    r = await client.post("/api/auth/refresh")
    assert r.status_code == 401
