"""Pydantic schemas for the auth endpoints."""
from __future__ import annotations

import uuid
from datetime import datetime

import phonenumbers
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.enums import UserRole


def _normalize_phone(raw: str) -> str:
    """Parse any reasonable phone input into strict E.164 (+countrycode + digits).

    Uses `is_possible_number` (length/region plausibility) rather than `is_valid_number`
    (which rejects reserved test ranges). Real validity is proven by OTP delivery.
    """
    if not raw:
        raise ValueError("phone is required")
    try:
        parsed = phonenumbers.parse(raw, None)
    except phonenumbers.NumberParseException as exc:
        raise ValueError(f"invalid phone format: {exc}") from exc
    if not phonenumbers.is_possible_number(parsed):
        raise ValueError("phone is not a possible number for any region")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


# ---------- Requests ----------


class RegisterRequest(BaseModel):
    phone: str = Field(..., description="E.164 phone number, e.g. +15551234567")
    name: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=8, max_length=128)
    role: UserRole = Field(..., description="Must be 'customer' or 'provider'")
    email: EmailStr | None = None
    # Provider-only fields (ignored for customer registration)
    service_type: str | None = Field(None, max_length=50)
    vehicle_info: str | None = Field(None, max_length=500)

    @field_validator("phone")
    @classmethod
    def _phone_e164(cls, v: str) -> str:
        return _normalize_phone(v)

    @field_validator("role")
    @classmethod
    def _role_not_admin(cls, v: UserRole) -> UserRole:
        if v == UserRole.admin:
            raise ValueError("admin accounts cannot self-register")
        return v


class VerifyOTPRequest(BaseModel):
    phone: str
    code: str = Field(..., min_length=4, max_length=10)

    @field_validator("phone")
    @classmethod
    def _phone_e164(cls, v: str) -> str:
        return _normalize_phone(v)


class LoginRequest(BaseModel):
    phone: str
    password: str = Field(..., min_length=1)

    @field_validator("phone")
    @classmethod
    def _phone_e164(cls, v: str) -> str:
        return _normalize_phone(v)


class RefreshRequest(BaseModel):
    """Refresh from JSON body — also supported via HttpOnly cookie."""
    refresh_token: str | None = None


# ---------- Responses ----------


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    phone: str
    name: str
    email: str | None
    role: UserRole
    is_active: bool
    is_phone_verified: bool
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    user: UserResponse


class MessageResponse(BaseModel):
    message: str
