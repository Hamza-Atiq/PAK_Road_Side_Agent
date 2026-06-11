"""Admin bootstrap and test-account creation endpoints.

All endpoints require X-Setup-Secret header matching ADMIN_SETUP_SECRET env var.
Disabled (404) when ADMIN_SETUP_SECRET is not set.
"""
from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.enums import UserRole
from app.models.provider import Provider
from app.models.user import User
from app.services.security import hash_password

router = APIRouter(prefix="/api/setup", tags=["setup"])

_ADMIN_PHONE = "+15550000001"
_ADMIN_NAME  = "System Admin"
_ADMIN_EMAIL = "admin@roadside.test"
_ADMIN_PASS  = "admin123"


def _require_secret(x_setup_secret: str | None) -> None:
    secret = os.environ.get("ADMIN_SETUP_SECRET", "")
    if not secret:
        raise HTTPException(status_code=404, detail="not found")
    if x_setup_secret != secret:
        raise HTTPException(status_code=403, detail="invalid secret")


class SetupRequest(BaseModel):
    force_reset: bool = False


class ResetUserRequest(BaseModel):
    phone: str
    new_password: str = "Reset1234!"


class CreateUserRequest(BaseModel):
    phone: str
    name: str
    password: str
    role: str = "customer"
    service_type: str | None = None
    vehicle_info: str | None = None
    force_recreate: bool = False


@router.post("/admin", status_code=201, summary="Bootstrap first admin (one-time use)")
async def bootstrap_admin(
    payload: SetupRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_setup_secret: Annotated[str | None, Header()] = None,
) -> dict:
    _require_secret(x_setup_secret)

    existing = await db.scalar(select(User).where(User.role == UserRole.admin.value))
    if existing:
        if payload.force_reset:
            existing.password_hash = hash_password(_ADMIN_PASS)
            existing.is_active = True
            existing.is_phone_verified = True
            await db.commit()
            return {"created": False, "reset": True, "admin_id": str(existing.id), "phone": existing.phone, "password": _ADMIN_PASS}
        return {"created": False, "admin_id": str(existing.id), "phone": existing.phone, "message": "admin exists — use force_reset=true to reset password"}

    admin = User(
        phone=_ADMIN_PHONE,
        name=_ADMIN_NAME,
        email=_ADMIN_EMAIL,
        role=UserRole.admin.value,
        password_hash=hash_password(_ADMIN_PASS),
        is_active=True,
        is_phone_verified=True,
    )
    db.add(admin)
    await db.commit()
    return {"created": True, "admin_id": str(admin.id), "phone": _ADMIN_PHONE, "password": _ADMIN_PASS}


@router.post("/reset-user", status_code=200, summary="Reset any user's password")
async def reset_user_password(
    payload: ResetUserRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_setup_secret: Annotated[str | None, Header()] = None,
) -> dict:
    _require_secret(x_setup_secret)

    user = await db.scalar(select(User).where(User.phone == payload.phone))
    if user is None:
        raise HTTPException(status_code=404, detail=f"no user with phone {payload.phone}")

    user.password_hash = hash_password(payload.new_password)
    user.is_active = True
    user.is_phone_verified = True
    await db.commit()
    return {"user_id": str(user.id), "phone": user.phone, "name": user.name, "role": user.role, "new_password": payload.new_password}


@router.post("/create-user", status_code=201, summary="Create any user/provider bypassing OTP")
async def create_user(
    payload: CreateUserRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_setup_secret: Annotated[str | None, Header()] = None,
) -> dict:
    """Create a fully-active user (customer, provider, or admin) without OTP.
    Use for test accounts, team members, demo accounts.
    For providers: also creates approved Provider profile.
    """
    _require_secret(x_setup_secret)

    try:
        role_enum = UserRole(payload.role)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid role '{payload.role}'. Must be: customer, provider, admin")

    if role_enum == UserRole.provider and not payload.service_type:
        raise HTTPException(status_code=400, detail="service_type required for provider role")

    existing = await db.scalar(select(User).where(User.phone == payload.phone))
    if existing:
        if not payload.force_recreate:
            # Just update password and activate
            existing.password_hash = hash_password(payload.password)
            existing.is_active = True
            existing.is_phone_verified = True
            if payload.name:
                existing.name = payload.name
            # Approve provider if role matches
            if existing.role == UserRole.provider.value:
                prov = await db.scalar(select(Provider).where(Provider.id == existing.id))
                if prov:
                    prov.is_approved = True
                    prov.is_available = True
            await db.commit()
            return {"created": False, "updated": True, "user_id": str(existing.id), "phone": existing.phone, "role": existing.role, "password": payload.password}
        # force_recreate: delete existing and re-create
        await db.delete(existing)
        await db.flush()

    user = User(
        phone=payload.phone,
        name=payload.name,
        role=role_enum.value,
        password_hash=hash_password(payload.password),
        is_active=True,
        is_phone_verified=True,
    )
    db.add(user)
    await db.flush()

    if role_enum == UserRole.provider:
        provider = Provider(
            id=user.id,
            service_type=payload.service_type,
            vehicle_info=payload.vehicle_info or "",
            is_available=True,
            is_approved=True,
        )
        db.add(provider)

    await db.commit()
    return {
        "created": True,
        "user_id": str(user.id),
        "phone": payload.phone,
        "name": payload.name,
        "role": role_enum.value,
        "password": payload.password,
        "approved": role_enum == UserRole.provider,
    }
