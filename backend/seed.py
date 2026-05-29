"""Seed the database with deterministic test data.

Run after `alembic upgrade head`:
    python backend/seed.py

Creates:
- 1 admin (phone +15550000001, password: admin123)
- 2 customers (phones +15551000001..2, password: customer123)
- 3 providers spread across known coordinates so KNN ordering is testable
  (phones +15552000001..3, password: provider123)

Idempotent — safe to run multiple times (uses ON CONFLICT logic).
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

# Make `backend/` importable when running this script directly
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models import Incident, Provider, User
from app.models.enums import ServiceType, UserRole
from app.services.security import hash_password

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("seed")

# All test locations are in San Francisco (good roadside-assistance density,
# clear KNN ordering when verifying nearest-provider queries).
SF_LAT, SF_LNG = 37.7749, -122.4194


SEED_DATA = {
    "admin": {
        "phone": "+15550000001",
        "name": "System Admin",
        "password": "admin123",
        "email": "admin@roadside.test",
    },
    "customers": [
        {"phone": "+15551000001", "name": "Alice Customer", "password": "customer123"},
        {"phone": "+15551000002", "name": "Bob Customer",   "password": "customer123"},
    ],
    "providers": [
        # Closest to SF downtown
        {
            "phone": "+15552000001", "name": "Tom Mechanic",
            "password": "provider123", "service_type": ServiceType.mechanic.value,
            "vehicle_info": "2022 Ford Transit, full toolkit",
            "lat": 37.7749, "lng": -122.4194,  # downtown SF
        },
        # ~3km away
        {
            "phone": "+15552000002", "name": "Sarah TowTruck",
            "password": "provider123", "service_type": ServiceType.tow_truck.value,
            "vehicle_info": "2021 Ford F-450, 10-ton tow capacity",
            "lat": 37.7849, "lng": -122.4094,
        },
        # ~7km away
        {
            "phone": "+15552000003", "name": "Mike TireBattery",
            "password": "provider123", "service_type": ServiceType.tire.value,
            "vehicle_info": "2023 Mercedes Sprinter, mobile tire + battery",
            "lat": 37.8049, "lng": -122.3894,
        },
    ],
}


async def _create_user(
    session: AsyncSession,
    *,
    phone: str,
    name: str,
    role: UserRole,
    password: str,
    email: str | None = None,
    is_active: bool = True,
) -> User:
    existing = await session.scalar(select(User).where(User.phone == phone))
    if existing:
        log.info(f"  - User {phone} already exists, skipping")
        return existing
    user = User(
        phone=phone,
        name=name,
        role=role.value,
        password_hash=hash_password(password),
        email=email,
        is_active=is_active,
        is_phone_verified=True,  # seed users are pre-verified
    )
    session.add(user)
    await session.flush()
    log.info(f"  + Created {role.value}: {phone} ({name})")
    return user


async def seed() -> None:
    async with AsyncSessionLocal() as session:
        log.info("Seeding admin...")
        await _create_user(
            session,
            phone=SEED_DATA["admin"]["phone"],
            name=SEED_DATA["admin"]["name"],
            role=UserRole.admin,
            password=SEED_DATA["admin"]["password"],
            email=SEED_DATA["admin"]["email"],
        )

        log.info("Seeding customers...")
        for c in SEED_DATA["customers"]:
            await _create_user(
                session,
                phone=c["phone"],
                name=c["name"],
                role=UserRole.customer,
                password=c["password"],
            )

        log.info("Seeding providers...")
        for p in SEED_DATA["providers"]:
            user = await _create_user(
                session,
                phone=p["phone"],
                name=p["name"],
                role=UserRole.provider,
                password=p["password"],
            )
            # Create provider row only if missing
            existing_prov = await session.get(Provider, user.id)
            if existing_prov:
                log.info(f"  - Provider profile for {p['phone']} already exists, skipping")
                continue
            provider = Provider(
                id=user.id,
                service_type=p["service_type"],
                vehicle_info=p["vehicle_info"],
                is_available=True,
                is_approved=True,
                # PostGIS Geography(POINT) input format: 'SRID=4326;POINT(lng lat)'
                location=f"SRID=4326;POINT({p['lng']} {p['lat']})",
            )
            session.add(provider)
            log.info(f"  + Provider profile @ ({p['lat']}, {p['lng']}) [{p['service_type']}]")

        await session.commit()
        log.info("Seed complete.")


async def verify_knn() -> None:
    """Sanity check: PostGIS KNN should return providers ordered by distance from SF downtown."""
    from sqlalchemy import text

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT u.name,
                       ST_Distance(
                           p.location,
                           ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography
                       ) / 1000.0 AS distance_km
                FROM providers p
                JOIN users u ON u.id = p.id
                WHERE p.is_available = TRUE
                ORDER BY p.location <-> ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography
                LIMIT 5
            """),
            {"lat": SF_LAT, "lng": SF_LNG},
        )
        log.info("KNN nearest providers from SF downtown (37.7749, -122.4194):")
        for row in result:
            log.info(f"  - {row.name}: {row.distance_km:.2f} km")


async def main() -> None:
    # Must share one event loop with the seed step. Two asyncio.run() calls
    # leave the module-level async engine's pool bound to the first (now-closed)
    # loop, and pool_pre_ping on the second call dies with "Event loop is closed".
    from app.database import engine
    try:
        await seed()
        await verify_knn()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
