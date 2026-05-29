"""Admin API integration tests — role guard, dashboard, query, reassign, suspend."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.base import AgentResult
from app.agents.communication import CommunicationResult
from app.models.enums import IncidentStatus, UserRole
from app.services.jwt_service import encode_access_token
from app.services.security import hash_password
from app.services.twilio_verify import DEV_OTP_CODE


async def _seed_user(db_session, *, role, phone, name="X"):
    from app.models.user import User
    u = User(
        phone=phone, name=name, role=role.value,
        password_hash=hash_password("password123"),
        is_active=True, is_phone_verified=True,
    )
    db_session.add(u)
    await db_session.flush()
    return u


def _auth_header(user) -> dict[str, str]:
    token = encode_access_token(user_id=user.id, role=user.role, phone=user.phone)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_dashboard_requires_admin(client, db_session):
    customer = await _seed_user(db_session, role=UserRole.customer, phone="+15557770001")
    resp = await client.get("/api/admin/dashboard", headers=_auth_header(customer))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_dashboard_returns_payload_for_admin(client, db_session):
    admin = await _seed_user(db_session, role=UserRole.admin, phone="+15557770099")
    resp = await client.get("/api/admin/dashboard", headers=_auth_header(admin))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "incidents_by_status" in body
    assert "providers" in body
    assert "messaging" in body
    assert "generated_at" in body


@pytest.mark.asyncio
async def test_unauthenticated_dashboard_rejected(client):
    resp = await client.get("/api/admin/dashboard")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_notify_endpoint_sends_message(client, db_session, monkeypatch):
    admin = await _seed_user(db_session, role=UserRole.admin, phone="+15557771099")
    resp = await client.post(
        "/api/admin/notify",
        headers=_auth_header(admin),
        json={"to_phone": "+15555550001", "body": "Test admin message"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "twilio_sid" in body
    # Dev mode: twilio_sid starts with dev-sid- (set in conftest)
    assert body["twilio_sid"].startswith("dev-sid-")


@pytest.mark.asyncio
async def test_admin_query_endpoint_calls_agent(client, db_session, monkeypatch):
    admin = await _seed_user(db_session, role=UserRole.admin, phone="+15557772099")

    # Monkeypatch AdminAgent to avoid Claude calls
    from app.agents import admin_agent as admin_agent_mod
    from app.agents.admin_agent import AdminAgentOutcome

    class FakeAgent:
        def __init__(self, *a, **kw):
            pass
        async def run(self, ctx):
            return AgentResult(
                success=True,
                output=AdminAgentOutcome(
                    intent="query_metrics",
                    summary="All systems nominal.",
                    data={"incidents_by_status": {"ASSIGNED": 0}},
                    actioned=False,
                ),
                agent_name="AdminAgent",
            )

    monkeypatch.setattr(admin_agent_mod, "AdminAgent", FakeAgent)
    # The router imports the class at request-time so we need to also patch where it's imported
    import app.api.admin as admin_api
    monkeypatch.setattr(admin_api, "AdminAgent", FakeAgent)

    resp = await client.post(
        "/api/admin/query",
        headers=_auth_header(admin),
        json={"query": "How are we doing?"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["intent"] == "query_metrics"
    assert "nominal" in body["summary"].lower()


@pytest.mark.asyncio
async def test_suspend_provider_endpoint(client, db_session):
    admin = await _seed_user(db_session, role=UserRole.admin, phone="+15557773099")
    # Seed a provider
    from app.models.provider import Provider
    from app.models.user import User
    prov_user = User(
        phone="+15557773001", name="ToSuspend",
        role=UserRole.provider.value,
        password_hash=hash_password("password123"),
        is_active=True, is_phone_verified=True,
    )
    db_session.add(prov_user)
    await db_session.flush()
    db_session.add(Provider(
        id=prov_user.id, service_type="mechanic",
        is_available=True, is_approved=True,
        location="SRID=4326;POINT(-122.4194 37.7749)",
    ))
    await db_session.flush()

    resp = await client.put(
        f"/api/admin/providers/{prov_user.id}/suspend",
        headers=_auth_header(admin),
        json={"reason": "abuse complaint"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["suspended"] is True
    await db_session.refresh(prov_user)
    assert prov_user.is_active is False


@pytest.mark.asyncio
async def test_approve_provider_endpoint(client, db_session):
    admin = await _seed_user(db_session, role=UserRole.admin, phone="+15557774099")
    from app.models.provider import Provider
    from app.models.user import User
    prov_user = User(
        phone="+15557774001", name="ToApprove",
        role=UserRole.provider.value,
        password_hash=hash_password("password123"),
        is_active=True, is_phone_verified=True,
    )
    db_session.add(prov_user)
    await db_session.flush()
    db_session.add(Provider(
        id=prov_user.id, service_type="mechanic",
        is_available=False, is_approved=False,
    ))
    await db_session.flush()

    resp = await client.put(
        f"/api/admin/providers/{prov_user.id}/approve",
        headers=_auth_header(admin),
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_suspend_unknown_provider_returns_404(client, db_session):
    admin = await _seed_user(db_session, role=UserRole.admin, phone="+15557775099")
    fake_id = uuid.uuid4()
    resp = await client.put(
        f"/api/admin/providers/{fake_id}/suspend",
        headers=_auth_header(admin),
        json={"reason": "x"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_admin_notify_invalid_phone_rejected(client, db_session):
    admin = await _seed_user(db_session, role=UserRole.admin, phone="+15557776099")
    resp = await client.post(
        "/api/admin/notify",
        headers=_auth_header(admin),
        json={"to_phone": "notaphone", "body": "x"},
    )
    assert resp.status_code == 422
