"""Integration tests for the Providers API."""
from __future__ import annotations

import pytest

from app.models.enums import UserRole
from app.services.jwt_service import encode_access_token
from app.services.security import hash_password


async def _seed_provider(db_session, *, phone="+15559990001", name="P",
                         is_available=False, is_approved=True):
    from app.models.provider import Provider
    from app.models.user import User
    u = User(
        phone=phone, name=name, role=UserRole.provider.value,
        password_hash=hash_password("password123"),
        is_active=True, is_phone_verified=True,
    )
    db_session.add(u)
    await db_session.flush()
    p = Provider(
        id=u.id, service_type="mechanic",
        is_available=is_available, is_approved=is_approved,
        location="SRID=4326;POINT(-122.4194 37.7749)",
    )
    db_session.add(p)
    await db_session.flush()
    return u, p


async def _seed_admin(db_session, phone="+15559990099"):
    from app.models.user import User
    u = User(
        phone=phone, name="A", role=UserRole.admin.value,
        password_hash=hash_password("password123"),
        is_active=True, is_phone_verified=True,
    )
    db_session.add(u)
    await db_session.flush()
    return u


def _auth(u) -> dict[str, str]:
    return {"Authorization": f"Bearer {encode_access_token(user_id=u.id, role=u.role, phone=u.phone)}"}


@pytest.mark.asyncio
async def test_get_me_returns_provider_profile(client, db_session):
    user, _ = await _seed_provider(db_session, phone="+15559991001")
    resp = await client.get("/api/providers/me", headers=_auth(user))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["service_type"] == "mechanic"
    assert body["is_approved"] is True


@pytest.mark.asyncio
async def test_put_me_updates_service_and_vehicle(client, db_session):
    user, _ = await _seed_provider(db_session, phone="+15559991002")
    resp = await client.put(
        "/api/providers/me", headers=_auth(user),
        json={"service_type": "tow_truck", "vehicle_info": "Ford F-450"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["service_type"] == "tow_truck"
    assert body["vehicle_info"] == "Ford F-450"


@pytest.mark.asyncio
async def test_availability_toggle_on_sets_last_ping(client, db_session):
    user, _ = await _seed_provider(db_session, phone="+15559991003")
    resp = await client.put(
        "/api/providers/availability", headers=_auth(user),
        json={"is_available": True},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_available"] is True
    assert body["last_ping"] is not None


@pytest.mark.asyncio
async def test_availability_blocked_when_not_approved(client, db_session):
    user, _ = await _seed_provider(db_session, phone="+15559991004", is_approved=False)
    resp = await client.put(
        "/api/providers/availability", headers=_auth(user),
        json={"is_available": True},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_location_ping_updates_postgis(client, db_session):
    user, _ = await _seed_provider(db_session, phone="+15559991005")
    resp = await client.post(
        "/api/providers/location", headers=_auth(user),
        json={"lat": 33.6844, "lng": 73.0479},  # Islamabad — verify global lat/lng work
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["last_ping"]
    # Verify via raw SQL that location moved
    from sqlalchemy import text
    row = await db_session.execute(
        text("SELECT ST_X(location::geometry) AS lng, ST_Y(location::geometry) AS lat "
             "FROM providers WHERE id = :id"),
        {"id": user.id},
    )
    r = row.first()
    assert abs(r.lat - 33.6844) < 0.0001
    assert abs(r.lng - 73.0479) < 0.0001


@pytest.mark.asyncio
async def test_location_ping_rejects_invalid_coords(client, db_session):
    user, _ = await _seed_provider(db_session, phone="+15559991006")
    resp = await client.post(
        "/api/providers/location", headers=_auth(user),
        json={"lat": 200, "lng": 999},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_admin_list_providers(client, db_session):
    admin = await _seed_admin(db_session)
    await _seed_provider(db_session, phone="+15559991007", name="One")
    await _seed_provider(db_session, phone="+15559991008", name="Two", is_available=True)
    resp = await client.get("/api/providers", headers=_auth(admin))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 2


@pytest.mark.asyncio
async def test_customer_cannot_list_providers(client, db_session):
    from app.models.user import User
    customer = User(
        phone="+15559991020", name="C", role=UserRole.customer.value,
        password_hash=hash_password("password123"),
        is_active=True, is_phone_verified=True,
    )
    db_session.add(customer)
    await db_session.flush()
    resp = await client.get("/api/providers", headers=_auth(customer))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_non_provider_cannot_post_location(client, db_session):
    admin = await _seed_admin(db_session, phone="+15559991030")
    resp = await client.post(
        "/api/providers/location", headers=_auth(admin),
        json={"lat": 1.0, "lng": 2.0},
    )
    assert resp.status_code == 403
