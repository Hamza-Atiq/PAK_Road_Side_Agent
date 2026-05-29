"""Providers API.

GET  /me           — provider's own profile
PUT  /me           — update service_type / vehicle_info
PUT  /availability — toggle on/off (also marks last_ping)
POST /location     — periodic GPS ping (every ~30s); updates PostGIS column
GET  /             — admin: list all providers
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import CurrentUser, require_role
from app.middleware.logging import get_logger
from app.models.enums import UserRole
from app.models.provider import Provider
from app.models.user import User
from app.schemas.provider import (
    AvailabilityRequest,
    LocationPingRequest,
    LocationPingResponse,
    ProviderListItem,
    ProviderListResponse,
    ProviderProfile,
    ProviderUpdateRequest,
)
from app.tools.notification_tool import broadcast_admin_event

log = get_logger("api.providers")

router = APIRouter(prefix="/api/providers", tags=["providers"])


# ----------------------------------------------------------------------
# GET /me  — own profile
# ----------------------------------------------------------------------


@router.get(
    "/me",
    response_model=ProviderProfile,
    summary="Get the current provider's profile",
    dependencies=[Depends(require_role(UserRole.provider))],
)
async def get_my_profile(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProviderProfile:
    provider = await db.get(Provider, user.id)
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="provider profile missing — contact support",
        )
    return ProviderProfile.model_validate(provider)


# ----------------------------------------------------------------------
# PUT /me  — update service_type / vehicle_info
# ----------------------------------------------------------------------


@router.put(
    "/me",
    response_model=ProviderProfile,
    summary="Update service type or vehicle info",
    dependencies=[Depends(require_role(UserRole.provider))],
)
async def update_my_profile(
    payload: ProviderUpdateRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProviderProfile:
    provider = await db.get(Provider, user.id)
    if provider is None:
        raise HTTPException(status_code=404, detail="provider profile not found")
    if payload.service_type is not None:
        provider.service_type = payload.service_type
    if payload.vehicle_info is not None:
        provider.vehicle_info = payload.vehicle_info
    await db.flush()
    log.info("provider_profile_updated", provider_id=str(user.id))
    return ProviderProfile.model_validate(provider)


# ----------------------------------------------------------------------
# PUT /availability  — toggle on/off
# ----------------------------------------------------------------------


@router.put(
    "/availability",
    response_model=ProviderProfile,
    summary="Toggle availability — providers go online/offline manually",
    dependencies=[Depends(require_role(UserRole.provider))],
)
async def set_availability(
    payload: AvailabilityRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProviderProfile:
    provider = await db.get(Provider, user.id)
    if provider is None:
        raise HTTPException(status_code=404, detail="provider profile not found")
    if not provider.is_approved:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="provider account not yet approved by admin",
        )
    provider.is_available = bool(payload.is_available)
    # Stamp a ping so the tracker doesn't immediately flag them as offline
    if payload.is_available:
        provider.last_ping = datetime.now(UTC)
    await db.flush()
    log.info(
        "provider_availability_changed",
        provider_id=str(user.id),
        is_available=provider.is_available,
    )
    return ProviderProfile.model_validate(provider)


# ----------------------------------------------------------------------
# POST /location  — periodic GPS ping
# ----------------------------------------------------------------------


@router.post(
    "/location",
    response_model=LocationPingResponse,
    summary="Update provider's GPS location (called every ~30s while available)",
    dependencies=[Depends(require_role(UserRole.provider))],
)
async def location_ping(
    payload: LocationPingRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LocationPingResponse:
    provider = await db.get(Provider, user.id)
    if provider is None:
        raise HTTPException(status_code=404, detail="provider profile not found")

    now = datetime.now(UTC)
    # PostGIS expects 'SRID=4326;POINT(lng lat)' — note longitude first.
    provider.location = f"SRID=4326;POINT({payload.lng} {payload.lat})"
    provider.last_ping = now
    await db.flush()

    # Tell the admin live map so the marker can move in real time
    await broadcast_admin_event(
        event="PROVIDER_LOCATION",
        agent="API",
        data={
            "provider_id": str(user.id),
            "lat": payload.lat,
            "lng": payload.lng,
            "is_available": provider.is_available,
        },
    )

    return LocationPingResponse(
        provider_id=user.id,
        last_ping=now,
        is_available=provider.is_available,
    )


# ----------------------------------------------------------------------
# GET /  (admin)  — list providers
# ----------------------------------------------------------------------


@router.get(
    "",
    response_model=ProviderListResponse,
    summary="Admin: list all providers",
    dependencies=[Depends(require_role(UserRole.admin))],
)
async def list_providers(
    db: Annotated[AsyncSession, Depends(get_db)],
    is_available: bool | None = None,
    is_approved: bool | None = None,
    service_type: str | None = None,
) -> ProviderListResponse:
    stmt = select(Provider, User).join(User, User.id == Provider.id)
    if is_available is not None:
        stmt = stmt.where(Provider.is_available.is_(is_available))
    if is_approved is not None:
        stmt = stmt.where(Provider.is_approved.is_(is_approved))
    if service_type:
        stmt = stmt.where(Provider.service_type == service_type)
    stmt = stmt.order_by(Provider.total_jobs.desc()).limit(200)
    rows = (await db.execute(stmt)).all()

    items = [
        ProviderListItem(
            id=p.id, name=u.name, phone=u.phone,
            service_type=p.service_type,
            is_available=p.is_available, is_approved=p.is_approved,
            total_jobs=p.total_jobs, last_ping=p.last_ping,
        )
        for (p, u) in rows
    ]
    return ProviderListResponse(total=len(items), items=items)
