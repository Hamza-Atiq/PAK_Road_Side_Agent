"""Security review test suite (Phase 16).

Each test asserts a specific defensive property of the production system:

1. Role gating — provider cannot read /api/admin/*; customer cannot read /api/admin/*.
2. Cross-provider isolation — provider A cannot fetch incident assigned to provider B.
3. Owner-or-admin — customer A cannot read incident owned by customer B.
4. Twilio webhook signature — in production-like mode, a missing/bad signature
   returns 403 and does NOT mutate the message row.
5. File upload validation — wrong MIME and oversize uploads are rejected.
6. JWT secrets/passwords never appear in logs or error responses.
7. Expired / malformed JWTs return 401.
8. /metrics is exposed (Prometheus needs it), but no PII leaks into label values.
"""
from __future__ import annotations

import io
import logging
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt as jose_jwt

from app.config import settings
from app.models.enums import IncidentStatus, MessageType, UserRole
from app.models.incident import Incident
from app.models.message import Message
from app.services.jwt_service import encode_access_token
from app.services.security import hash_password


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 1024
HTML_BYTES = b"<html><body>not an image</body></html>"


# ============================================================
# Fixtures (lightweight inline helpers)
# ============================================================


async def _seed_user(db_session, *, role: UserRole, phone: str, name: str = "Test"):
    from app.models.user import User
    user = User(
        phone=phone, name=name, role=role.value,
        password_hash=hash_password("password123"),
        is_active=True, is_phone_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def _seed_provider(db_session, *, phone: str, name: str = "Provider"):
    from app.models.provider import Provider
    user = await _seed_user(db_session, role=UserRole.provider, phone=phone, name=name)
    prov = Provider(
        id=user.id, service_type="mechanic",
        is_available=True, is_approved=True,
        location="SRID=4326;POINT(-122.4194 37.7749)",
    )
    db_session.add(prov)
    await db_session.flush()
    return user, prov


async def _seed_incident(db_session, *, customer_id, provider_id=None,
                          status: IncidentStatus = IncidentStatus.REPORTED):
    inc = Incident(
        customer_id=customer_id, provider_id=provider_id,
        lat=37.7749, lng=-122.4194,
        description="test", status=status.value,
    )
    db_session.add(inc)
    await db_session.flush()
    return inc


def _auth(user) -> dict[str, str]:
    return {"Authorization": f"Bearer {encode_access_token(user_id=user.id, role=user.role, phone=user.phone)}"}


# ============================================================
# 1. Role gating
# ============================================================


@pytest.mark.asyncio
async def test_provider_cannot_access_admin_endpoint(client, db_session):
    provider, _ = await _seed_provider(db_session, phone="+15557770001")
    resp = await client.get("/api/admin/dashboard", headers=_auth(provider))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_customer_cannot_access_admin_endpoint(client, db_session):
    customer = await _seed_user(db_session, role=UserRole.customer, phone="+15557770002")
    resp = await client.get("/api/admin/dashboard", headers=_auth(customer))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_anonymous_cannot_create_incident(client):
    resp = await client.post(
        "/api/incidents",
        data={"lat": "37.7", "lng": "-122.4", "description": "anon"},
    )
    assert resp.status_code == 401


# ============================================================
# 2. Cross-provider isolation
# ============================================================


@pytest.mark.asyncio
async def test_provider_cannot_read_other_providers_incident(client, db_session):
    customer = await _seed_user(db_session, role=UserRole.customer, phone="+15557771001")
    provider_a, _ = await _seed_provider(db_session, phone="+15557771002", name="A")
    provider_b, _ = await _seed_provider(db_session, phone="+15557771003", name="B")

    # Incident assigned to provider A
    inc = await _seed_incident(
        db_session, customer_id=customer.id, provider_id=provider_a.id,
        status=IncidentStatus.ASSIGNED,
    )
    # Provider B asks for it
    resp = await client.get(f"/api/incidents/{inc.id}", headers=_auth(provider_b))
    assert resp.status_code == 403, \
        f"provider B must not see provider A's incident: {resp.status_code} {resp.text}"


# ============================================================
# 3. Owner-or-admin gating
# ============================================================


@pytest.mark.asyncio
async def test_customer_cannot_read_other_customers_incident(client, db_session):
    customer_a = await _seed_user(db_session, role=UserRole.customer, phone="+15557772001")
    customer_b = await _seed_user(db_session, role=UserRole.customer, phone="+15557772002")
    inc = await _seed_incident(db_session, customer_id=customer_a.id)
    resp = await client.get(f"/api/incidents/{inc.id}", headers=_auth(customer_b))
    assert resp.status_code == 403


# ============================================================
# 4. Twilio webhook signature
# ============================================================


@pytest.mark.asyncio
async def test_twilio_webhook_rejects_bad_signature_in_prod(client, db_session, monkeypatch):
    """Outside dev fallback, a missing/forged signature returns 403 and DOES NOT
    mutate the Message row. Inside dev fallback (default in tests), signature
    validation returns True — we simulate prod here by forcing it False."""
    msg = Message(
        msg_type=MessageType.SMS.value,
        content="confidential",
        recipient_phone="+15551234567",
        twilio_sid="SM_bad_sig_001",
        delivery_status="SENT",
    )
    db_session.add(msg)
    await db_session.flush()

    # NB: `app.api.webhooks` imports `validate_signature` by name, so we have
    # to patch the binding inside that module — not the source module.
    from app.services import twilio_service
    from app.api import webhooks as webhooks_mod
    monkeypatch.setattr(twilio_service, "validate_signature", lambda **kw: False)
    monkeypatch.setattr(webhooks_mod, "validate_signature", lambda **kw: False)

    resp = await client.post(
        "/api/webhooks/twilio/sms-status",
        data={
            "MessageSid": "SM_bad_sig_001",
            "MessageStatus": "delivered",
            "To": "+15551234567",
        },
        # No X-Twilio-Signature header
    )
    assert resp.status_code == 403
    # Row must still be SENT — webhook must not mutate before signature check
    await db_session.refresh(msg)
    assert msg.delivery_status == "SENT"


# ============================================================
# 5. File upload validation
# ============================================================


@pytest.mark.asyncio
async def test_upload_rejects_html_disguised_as_image(client, db_session, monkeypatch, tmp_path):
    customer = await _seed_user(db_session, role=UserRole.customer, phone="+15557774001")
    # Avoid Celery enqueue + redirect upload dir
    monkeypatch.setattr(
        "app.tasks.incident_tasks.process_incident_task.delay",
        lambda *args, **kwargs: None,
    )
    from app.services import file_service
    monkeypatch.setattr(file_service.settings, "UPLOAD_DIR", str(tmp_path))

    resp = await client.post(
        "/api/incidents",
        headers=_auth(customer),
        data={"lat": "37.7", "lng": "-122.4", "description": "phishing test"},
        files={"image": ("evil.png", io.BytesIO(HTML_BYTES), "image/png")},
    )
    assert resp.status_code == 400
    assert "MIME" in resp.text or "unsupported" in resp.text.lower()


@pytest.mark.asyncio
async def test_upload_rejects_oversize_payload(client, db_session, monkeypatch, tmp_path):
    customer = await _seed_user(db_session, role=UserRole.customer, phone="+15557774002")
    monkeypatch.setattr(
        "app.tasks.incident_tasks.process_incident_task.delay",
        lambda *args, **kwargs: None,
    )
    from app.services import file_service
    monkeypatch.setattr(file_service.settings, "UPLOAD_DIR", str(tmp_path))
    # Override MAX_UPLOAD_MB to 1 byte equivalent so the assertion is fast
    monkeypatch.setattr(file_service.settings, "MAX_UPLOAD_MB", 0)  # max_upload_bytes = 0

    resp = await client.post(
        "/api/incidents",
        headers=_auth(customer),
        data={"lat": "37.7", "lng": "-122.4", "description": "too big"},
        files={"image": ("car.png", io.BytesIO(PNG_BYTES), "image/png")},
    )
    assert resp.status_code == 400
    assert "too large" in resp.text.lower()


# ============================================================
# 6. Secrets never appear in logs / error responses
# ============================================================


@pytest.mark.asyncio
async def test_password_not_echoed_in_login_error(client):
    """The plaintext password must never appear in a failed-login response."""
    secret_password = "super-secret-do-not-leak"
    resp = await client.post(
        "/api/auth/login",
        json={"phone": "+15559999999", "password": secret_password},
    )
    assert resp.status_code == 401
    assert secret_password not in resp.text


@pytest.mark.asyncio
async def test_jwt_secret_not_in_login_error(client, caplog):
    """JWT_SECRET_KEY must never leak into log records on a failed login."""
    with caplog.at_level(logging.DEBUG):
        await client.post(
            "/api/auth/login",
            json={"phone": "+15559999998", "password": "wrong"},
        )
    for record in caplog.records:
        msg = record.getMessage()
        assert settings.JWT_SECRET_KEY not in msg, \
            f"JWT secret leaked in log record: {record.name} / {msg[:80]}"


# ============================================================
# 7. JWT validation
# ============================================================


@pytest.mark.asyncio
async def test_malformed_jwt_returns_401(client):
    resp = await client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer not-a-real-jwt"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_expired_jwt_returns_401(client, db_session):
    user = await _seed_user(db_session, role=UserRole.customer, phone="+15557776001")
    # Craft an expired token with the same secret/algorithm
    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "phone": user.phone,
        "iat": int((now - timedelta(hours=2)).timestamp()),
        "exp": int((now - timedelta(hours=1)).timestamp()),
        "type": "access",
    }
    expired_token = jose_jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM,
    )
    resp = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_token_signed_with_wrong_secret_returns_401(client, db_session):
    user = await _seed_user(db_session, role=UserRole.customer, phone="+15557776002")
    bad_token = jose_jwt.encode(
        {
            "sub": str(user.id),
            "role": user.role,
            "phone": user.phone,
            "iat": int(datetime.now(tz=timezone.utc).timestamp()),
            "exp": int((datetime.now(tz=timezone.utc) + timedelta(hours=1)).timestamp()),
            "type": "access",
        },
        "wrong-secret-that-isn't-the-real-one-totally-fake-32b-long",
        algorithm=settings.JWT_ALGORITHM,
    )
    resp = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {bad_token}"},
    )
    assert resp.status_code == 401


# ============================================================
# 8. /metrics surface — exposed but no PII
# ============================================================


@pytest.mark.asyncio
async def test_metrics_endpoint_exposes_prometheus_format(client):
    resp = await client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers.get("content-type", "")
    body = resp.text
    # Some core metric names must be present
    assert "agent_calls_total" in body or "incidents_created_total" in body


@pytest.mark.asyncio
async def test_metrics_does_not_leak_phone_numbers(client, db_session):
    customer = await _seed_user(db_session, role=UserRole.customer, phone="+15557777999")
    # No phone number labels should appear in Prometheus output — labels stay
    # high-cardinality-free.
    resp = await client.get("/metrics")
    assert "+15557777999" not in resp.text
    assert customer.phone not in resp.text


# ============================================================
# 9. SQL injection sanity — IDs are validated as UUIDs
# ============================================================


@pytest.mark.asyncio
async def test_sqli_in_incident_id_returns_422(client, db_session):
    customer = await _seed_user(db_session, role=UserRole.customer, phone="+15557778001")
    resp = await client.get(
        "/api/incidents/' OR 1=1 --",
        headers=_auth(customer),
    )
    assert resp.status_code in (404, 422), \
        f"path-validator should reject non-UUID before hitting DB: {resp.status_code}"
