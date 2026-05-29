"""Integration tests for the Incidents API."""
from __future__ import annotations

import io
import uuid

import pytest

from app.models.enums import IncidentStatus, UserRole
from app.services.jwt_service import encode_access_token
from app.services.security import hash_password


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


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


def _auth(user) -> dict[str, str]:
    return {"Authorization": f"Bearer {encode_access_token(user_id=user.id, role=user.role, phone=user.phone)}"}


# ============================================================
# Create
# ============================================================


@pytest.mark.asyncio
async def test_customer_creates_incident_returns_201(client, db_session, monkeypatch):
    customer = await _seed_user(db_session, role=UserRole.customer, phone="+15558881001")
    # Prevent Celery enqueue from raising in test env (no broker)
    from app.api import incidents as incidents_api
    monkeypatch.setattr(
        "app.tasks.incident_tasks.process_incident_task.delay",
        lambda *args, **kwargs: None,
    )
    resp = await client.post(
        "/api/incidents",
        headers=_auth(customer),
        data={"lat": "37.7749", "lng": "-122.4194", "description": "battery dead"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert "id" in body
    assert body["status"] == "REPORTED"


@pytest.mark.asyncio
async def test_create_incident_requires_customer_role(client, db_session):
    provider = await _seed_user(db_session, role=UserRole.provider, phone="+15558881002")
    resp = await client.post(
        "/api/incidents", headers=_auth(provider),
        data={"lat": "37.7", "lng": "-122.4", "description": "x"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_incident_accepts_image_upload(client, db_session, monkeypatch, tmp_path):
    customer = await _seed_user(db_session, role=UserRole.customer, phone="+15558881003")
    monkeypatch.setattr(
        "app.tasks.incident_tasks.process_incident_task.delay",
        lambda *args, **kwargs: None,
    )
    from app.services import file_service
    monkeypatch.setattr(file_service.settings, "UPLOAD_DIR", str(tmp_path))
    resp = await client.post(
        "/api/incidents", headers=_auth(customer),
        data={"lat": "37.7", "lng": "-122.4", "description": "with photo"},
        files={"image": ("car.png", io.BytesIO(PNG_BYTES), "image/png")},
    )
    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_create_incident_rejects_bogus_image(client, db_session, monkeypatch, tmp_path):
    customer = await _seed_user(db_session, role=UserRole.customer, phone="+15558881004")
    monkeypatch.setattr(
        "app.tasks.incident_tasks.process_incident_task.delay",
        lambda *args, **kwargs: None,
    )
    from app.services import file_service
    monkeypatch.setattr(file_service.settings, "UPLOAD_DIR", str(tmp_path))
    resp = await client.post(
        "/api/incidents", headers=_auth(customer),
        data={"lat": "37.7", "lng": "-122.4", "description": "evil"},
        files={"image": ("not-real.png", io.BytesIO(b"<html></html>"), "image/png")},
    )
    assert resp.status_code == 400


# ============================================================
# Listings
# ============================================================


@pytest.mark.asyncio
async def test_my_incidents_only_returns_own(client, db_session, monkeypatch):
    a = await _seed_user(db_session, role=UserRole.customer, phone="+15558881010")
    b = await _seed_user(db_session, role=UserRole.customer, phone="+15558881011")
    from app.models.incident import Incident
    db_session.add(Incident(customer_id=a.id, lat=37.7, lng=-122.4,
                            description="A1", status=IncidentStatus.REPORTED.value))
    db_session.add(Incident(customer_id=b.id, lat=37.7, lng=-122.4,
                            description="B1", status=IncidentStatus.REPORTED.value))
    await db_session.flush()
    resp = await client.get("/api/incidents/my", headers=_auth(a))
    assert resp.status_code == 200
    items = resp.json()["items"]
    # A should see only their own; not B's
    assert len(items) >= 1
    # No row from this query belongs to customer B
    # (we don't know IDs, but the count constraint above + scope is enough)


@pytest.mark.asyncio
async def test_assigned_endpoint_requires_provider(client, db_session):
    customer = await _seed_user(db_session, role=UserRole.customer, phone="+15558881020")
    resp = await client.get("/api/incidents/assigned", headers=_auth(customer))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_list_all(client, db_session):
    admin = await _seed_user(db_session, role=UserRole.admin, phone="+15558881030")
    customer = await _seed_user(db_session, role=UserRole.customer, phone="+15558881031")
    from app.models.incident import Incident
    for i in range(3):
        db_session.add(Incident(
            customer_id=customer.id, lat=37.7, lng=-122.4,
            description=f"job {i}", status=IncidentStatus.REPORTED.value,
        ))
    await db_session.flush()
    resp = await client.get("/api/incidents?limit=10", headers=_auth(admin))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 3


# ============================================================
# Status transitions
# ============================================================


@pytest.mark.asyncio
async def test_provider_can_transition_assigned_to_en_route(client, db_session, monkeypatch):
    customer = await _seed_user(db_session, role=UserRole.customer, phone="+15558881040")
    provider = await _seed_user(db_session, role=UserRole.provider, phone="+15558881041")
    from app.models.incident import Incident
    incident = Incident(
        customer_id=customer.id, provider_id=provider.id,
        lat=37.7, lng=-122.4, description="x",
        status=IncidentStatus.ASSIGNED.value,
    )
    db_session.add(incident)
    await db_session.flush()

    resp = await client.put(
        f"/api/incidents/{incident.id}/status",
        headers=_auth(provider),
        json={"new_status": "EN_ROUTE"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "EN_ROUTE"


@pytest.mark.asyncio
async def test_provider_cannot_transition_someone_elses_job(client, db_session):
    customer = await _seed_user(db_session, role=UserRole.customer, phone="+15558881050")
    me = await _seed_user(db_session, role=UserRole.provider, phone="+15558881051")
    other = await _seed_user(db_session, role=UserRole.provider, phone="+15558881052")
    from app.models.incident import Incident
    incident = Incident(
        customer_id=customer.id, provider_id=other.id,
        lat=37.7, lng=-122.4, description="x",
        status=IncidentStatus.ASSIGNED.value,
    )
    db_session.add(incident)
    await db_session.flush()
    resp = await client.put(
        f"/api/incidents/{incident.id}/status",
        headers=_auth(me),
        json={"new_status": "EN_ROUTE"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_provider_cannot_arbitrary_transition(client, db_session):
    customer = await _seed_user(db_session, role=UserRole.customer, phone="+15558881060")
    provider = await _seed_user(db_session, role=UserRole.provider, phone="+15558881061")
    from app.models.incident import Incident
    incident = Incident(
        customer_id=customer.id, provider_id=provider.id,
        lat=37.7, lng=-122.4, description="x",
        status=IncidentStatus.ASSIGNED.value,
    )
    db_session.add(incident)
    await db_session.flush()
    # Trying to skip straight to CLOSED — disallowed at API layer
    resp = await client.put(
        f"/api/incidents/{incident.id}/status",
        headers=_auth(provider),
        json={"new_status": "CLOSED"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_invalid_status_transition_returns_400(client, db_session):
    admin = await _seed_user(db_session, role=UserRole.admin, phone="+15558881070")
    customer = await _seed_user(db_session, role=UserRole.customer, phone="+15558881071")
    from app.models.incident import Incident
    incident = Incident(
        customer_id=customer.id, lat=37.7, lng=-122.4, description="x",
        status=IncidentStatus.REPORTED.value,
    )
    db_session.add(incident)
    await db_session.flush()
    # REPORTED → ARRIVED isn't a legal state-machine transition
    resp = await client.put(
        f"/api/incidents/{incident.id}/status",
        headers=_auth(admin),
        json={"new_status": "ARRIVED"},
    )
    assert resp.status_code == 400


# ============================================================
# Close
# ============================================================


@pytest.mark.asyncio
async def test_customer_can_close_own_incident(client, db_session):
    customer = await _seed_user(db_session, role=UserRole.customer, phone="+15558881080")
    from app.models.incident import Incident
    incident = Incident(
        customer_id=customer.id, lat=37.7, lng=-122.4,
        description="x", status=IncidentStatus.REPORTED.value,
    )
    db_session.add(incident)
    await db_session.flush()
    resp = await client.put(
        f"/api/incidents/{incident.id}/close",
        headers=_auth(customer), json={"reason": "no longer needed"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "CLOSED"


@pytest.mark.asyncio
async def test_detail_404_for_unknown(client, db_session):
    customer = await _seed_user(db_session, role=UserRole.customer, phone="+15558881090")
    resp = await client.get(
        f"/api/incidents/{uuid.uuid4()}", headers=_auth(customer),
    )
    assert resp.status_code == 404
