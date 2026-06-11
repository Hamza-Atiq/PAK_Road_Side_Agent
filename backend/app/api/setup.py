"""One-time admin bootstrap endpoint.

POST /api/setup/admin
  Header: X-Setup-Secret: <value of ADMIN_SETUP_SECRET env var>

Creates the first admin user if one doesn't exist yet.
Disabled (404) when ADMIN_SETUP_SECRET is not set in the environment.
"""
from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.enums import UserRole
from app.models.user import User
from app.services.security import hash_password

router = APIRouter(prefix="/api/setup", tags=["setup"])

_ADMIN_PHONE = "+15550000001"
_ADMIN_NAME  = "System Admin"
_ADMIN_EMAIL = "admin@roadside.test"
_ADMIN_PASS  = "admin123"


@router.post("/admin", status_code=201, summary="Bootstrap first admin (one-time use)")
async def bootstrap_admin(
    db: Annotated[AsyncSession, Depends(get_db)],
    x_setup_secret: Annotated[str | None, Header()] = None,
) -> dict:
    secret = os.environ.get("ADMIN_SETUP_SECRET", "")
    if not secret:
        raise HTTPException(status_code=404, detail="not found")
    if x_setup_secret != secret:
        raise HTTPException(status_code=403, detail="invalid secret")

    existing = await db.scalar(select(User).where(User.role == UserRole.admin.value))
    if existing:
        return {"created": False, "admin_id": str(existing.id), "message": "admin already exists"}

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
